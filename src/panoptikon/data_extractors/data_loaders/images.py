import io
import logging
import os
import sqlite3
from typing import Any, List, Sequence, Union

import numpy as np
from attr import dataclass
from PIL import Image as PILImage
from PIL import ImageSequence

from panoptikon.data_extractors.data_loaders.pdf import read_pdf
from panoptikon.data_extractors.data_loaders.video import video_to_frames
from panoptikon.data_extractors.types import JobInputData
from panoptikon.db.storage import (
    get_frames_bytes,
    store_frames,
    thumbnail_to_bytes,
)

logger = logging.getLogger(__name__)


def gif_to_frames(path: str) -> List[PILImage.Image]:
    gif = PILImage.open(path)
    frames = []

    # Count the total number of frames
    total_frames = 0
    for _ in ImageSequence.Iterator(gif):
        total_frames += 1

    # Calculate the step to get 4 evenly spaced frames
    step = max(total_frames // 4, 1)

    # Extract 4 evenly spaced frames
    for i, frame in enumerate(ImageSequence.Iterator(gif)):
        if i % step == 0:
            frames.append(frame.copy())
        if len(frames) == 4:  # Stop after extracting 4 frames
            break

    return frames


@dataclass
class ImageSliceSettings:
    ratio_larger: int = 16
    ratio_smaller: int = 9
    max_multiplier: float = 2.0
    target_multiplier: float = 1.5


def image_loader(
    conn: sqlite3.Connection,
    item: JobInputData,
    slice_settings: ImageSliceSettings | None = ImageSliceSettings(),
) -> Sequence[bytes]:
    if item.type.startswith("image/gif"):
        return slice_target_size(
            [
                thumbnail_to_bytes(frame, "JPEG")
                for frame in gif_to_frames(item.path)
            ],
            item.width,
            item.height,
            slice_settings,
        )
    if item.type.startswith("image"):
        # Load image as bytes
        with open(item.path, "rb") as f:
            return slice_target_size(
                [f.read()],
                item.width,
                item.height,
                slice_settings,
            )
    if item.type.startswith("video"):
        if frames := get_frames_bytes(conn, item.sha256):
            logger.debug(f"Loaded {len(frames)} frames from database")
        else:
            if item.duration is None or item.duration == 0:
                logger.debug(f"Video {item.sha256} has no duration, skipping")
                return []
            if item.video_tracks is None or item.video_tracks == 0:
                logger.debug(
                    f"Video {item.sha256} has no video tracks, skipping"
                )
                return []
            pil_frames = video_to_frames(item.path, num_frames=4)
            frames = store_frames(
                conn,
                item.sha256,
                file_mime_type=item.type,
                process_version=1,
                frames=pil_frames,
            )
        return slice_target_size(
            frames,
            item.width,
            item.height,
            slice_settings,
        )

    if item.type.startswith("application/pdf"):
        pages_pil = [PILImage.fromarray(page) for page in read_pdf(item.path)]
        pages_slices = [
            slice_target_size(
                [thumbnail_to_bytes(page, "JPEG")],
                page.width,
                page.height,
                slice_settings,
            )
            for page in pages_pil
        ]
        return [s for page_slices in pages_slices for s in page_slices]
    if item.type.startswith("text/html"):
        res = read_html(item.path)
        assert res is not None, "Failed to read HTML file"
        pages_pil = [PILImage.fromarray(page) for page in read_pdf(res)]
        pages_slices = [
            slice_target_size(
                [thumbnail_to_bytes(page, "JPEG")],
                page.width,
                page.height,
                slice_settings,
            )
            for page in pages_pil
        ]
        return [s for page_slices in pages_slices for s in page_slices]
    return []


def get_pdf_image(file_path: str) -> PILImage.Image:

    return PILImage.fromarray(read_pdf(file_path)[0])


def read_html(url: str, **kwargs: Any) -> bytes | None:
    from weasyprint import HTML

    """Read a PDF file and convert it into an image in numpy format
    
    Args:
    ----
        url: URL of the target web page
        **kwargs: keyword arguments from `weasyprint.HTML`

    Returns:
    -------
        decoded PDF file as a bytes stream
    """
    return HTML(url, **kwargs).write_pdf()


def get_html_image(file_path: str) -> PILImage.Image:
    res = read_html(file_path)
    assert res is not None, "Failed to read HTML file"
    return PILImage.fromarray(read_pdf(res)[0])


def generate_thumbnail(
    image_path,
    max_dimensions=(4096, 4096),
    max_file_size=24 * 1024 * 1024,
):
    """
    Generates a thumbnail for an overly large image.

    Parameters:
    - image_path (str): Path to the original image.
    - thumbnail_path (str): Path where the thumbnail will be saved.
    - max_dimensions (tuple): Maximum width and height for an image to be considered overly large.
    - max_file_size (int): Maximum file size (in bytes) for an image to be considered overly large.

    Returns:
    - bool: True if a thumbnail was created, False if the image was not overly large.
    """
    really_small_file_size = 5 * 1024 * 1024  # 5 MB
    # Check if the image is overly large based on file size
    file_size = os.path.getsize(image_path)
    if file_size <= really_small_file_size:
        return None

    img = PILImage.open(image_path)
    # Check if the image is overly large based on dimensions
    if (
        img.size[0] <= max_dimensions[0]
        and img.size[1] <= max_dimensions[1]
        and file_size <= max_file_size
    ):
        return None

    # Generate thumbnail
    img.thumbnail(max_dimensions, PILImage.Resampling.LANCZOS)
    return img


def slice_target_size(
    input_images: List[bytes],
    width: int | None,
    height: int | None,
    settings: ImageSliceSettings | None,
) -> List[bytes]:
    if (
        width is None
        or height is None
        or settings is None
        or not is_excessive_ratio(width, height, settings)
    ):
        return input_images

    n_slices = calculate_slices_needed(width, height, settings)
    logger.debug(
        f"Image has an excessive aspect ratio ({width}x{height}), slicing into {n_slices} pieces..."
    )
    output_slices = []
    for image in input_images:
        slices = slice_image(image, n_slices)
        for s in slices:
            output_slices.append(s)
    return output_slices


def is_excessive_ratio(
    image_width: int,
    image_height: int,
    ratio_settings: ImageSliceSettings = ImageSliceSettings(),
) -> bool:
    """
    Determines if an image has an excessive aspect ratio compared to a target ratio.
    The larger ratio number always applies to the longer dimension of the image.

    Args:
        image_width (int): Width of the image in pixels
        image_height (int): Height of the image in pixels
        ratio_larger (int): Larger number of the target ratio (default 16)
        ratio_smaller (int): Smaller number of the target ratio (default 9)
        max_multiplier (float): How many times the target ratio is allowed (default 2.0)

    Returns:
        bool: True if the image exceeds the maximum allowed ratio, False otherwise
    """
    # Calculate the actual ratio of the image (always larger divided by smaller)
    if image_width >= image_height:
        image_ratio = image_width / image_height
    else:
        image_ratio = image_height / image_width

    # Target ratio is always larger divided by smaller
    target_ratio = ratio_settings.ratio_larger / ratio_settings.ratio_smaller

    # Check if image ratio exceeds the target ratio multiplied by max_multiplier
    return image_ratio > (target_ratio * ratio_settings.max_multiplier)


def calculate_slices_needed(
    image_width: int, image_height: int, settings: ImageSliceSettings
) -> int:
    """
    Calculates number of slices needed to divide an image into pieces with target aspect ratios.
    Will slice if ratio exceeds max_multiplier, and will slice to achieve target_multiplier.

    Args:
        image_width (int): Width of the image in pixels
        image_height (int): Height of the image in pixels
        settings (ImageSliceSettings): Settings for ratio and multiplier values

    Returns:
        int: Number of slices needed (1 if no slicing needed)
    """
    # Determine orientation and calculate ratio
    is_landscape = image_width >= image_height
    if is_landscape:
        image_ratio = image_width / image_height
    else:
        image_ratio = image_height / image_width

    base_ratio = settings.ratio_larger / settings.ratio_smaller
    max_acceptable_ratio = base_ratio * settings.max_multiplier
    target_ratio = base_ratio * settings.target_multiplier

    # If ratio is acceptable, return 1 (no slicing needed)
    if image_ratio <= max_acceptable_ratio:
        return 1

    # Calculate number of slices needed to achieve target ratio
    from math import ceil

    return ceil(image_ratio / target_ratio)


def slice_image(
    image: Union[str, bytes, PILImage.Image], num_slices: int
) -> List[bytes]:
    """
    Slices an image into equal parts along its longest dimension.
    Maintains the original image format.

    Args:
        image: Can be a file path (str), bytes of image file, or PIL Image object
        num_slices: Number of slices to create

    Returns:
        List of bytes objects, each containing an encoded image slice
    """
    # Convert input to PIL Image if needed
    if isinstance(image, str):
        img = PILImage.open(image)
        format = img.format
    elif isinstance(image, bytes):
        img = PILImage.open(io.BytesIO(image))
        format = img.format
    elif isinstance(image, PILImage.Image):
        format = image.format or "PNG"  # Default to PNG if format is None
        img = image
    else:
        raise ValueError(
            "Image must be a file path, bytes, or PIL Image object"
        )

    # Get dimensions and determine slice direction
    width, height = img.size
    is_landscape = width >= height

    slices = []

    if is_landscape:
        # Slice vertically
        slice_width = width // num_slices
        for i in range(num_slices):
            start = i * slice_width
            # For last slice, use full remaining width to handle rounding
            end = start + slice_width if i < num_slices - 1 else width

            # Crop and convert to bytes
            slice_img = img.crop((start, 0, end, height))
            buffer = io.BytesIO()
            slice_img.save(buffer, format=format)
            slices.append(buffer.getvalue())
    else:
        # Slice horizontally
        slice_height = height // num_slices
        for i in range(num_slices):
            start = i * slice_height
            # For last slice, use full remaining height to handle rounding
            end = start + slice_height if i < num_slices - 1 else height

            # Crop and convert to bytes
            slice_img = img.crop((0, start, width, end))
            buffer = io.BytesIO()
            slice_img.save(buffer, format=format)
            slices.append(buffer.getvalue())

    # Close the image if we opened it
    if isinstance(image, (str, bytes)):
        img.close()

    # Random filename for debugging
    # filename = f"{np.random.randint(0, 1000)}-{np.random.randint(0, 1000)}"
    # save_images_to_disk(slices, filename)
    return slices


def save_images_to_disk(images: List[bytes], name: str = "slice") -> None:
    """
    Save a list of images to disk as files.

    Args:
        images (List[bytes]): List of image bytes to save
    """
    for i, image in enumerate(images):
        with open(f"scripts/slices/{name}-s_{i}.jpg", "wb") as f:
            f.write(image)
