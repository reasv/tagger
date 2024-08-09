import os
from typing import List

import numpy as np
from doctr.io.html import read_html
from doctr.io.pdf import read_pdf
from PIL import Image as PILImage
from PIL import ImageSequence

from src.data_extractors.data_loaders.video import video_to_frames
from src.types import ItemWithPath
from src.utils import pil_ensure_rgb


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


def item_image_loader_numpy(item: ItemWithPath) -> List[np.ndarray]:
    if item.type.startswith("image/gif"):
        return [
            np.array(pil_ensure_rgb(frame))
            for frame in gif_to_frames(item.path)
        ]
    if item.type.startswith("image"):
        return [np.array(pil_ensure_rgb(PILImage.open(item.path)))]
    if item.type.startswith("video"):
        frames = video_to_frames(item.path, num_frames=4)
        return [np.array(pil_ensure_rgb(frame)) for frame in frames]
    if item.type.startswith("application/pdf"):
        return read_pdf(item.path)
    if item.type.startswith("text/html"):
        return read_pdf(read_html(item.path))
    return []


def item_image_loader_pillow(item: ItemWithPath) -> List[PILImage.Image]:
    if item.type.startswith("image/gif"):
        return [frame for frame in gif_to_frames(item.path)]
    if item.type.startswith("image"):
        return [PILImage.open(item.path)]
    if item.type.startswith("video"):
        frames = video_to_frames(item.path, num_frames=4)
        return frames
    if item.type.startswith("application/pdf"):
        return [PILImage.fromarray(page) for page in read_pdf(item.path)]
    if item.type.startswith("text/html"):
        return [
            PILImage.fromarray(page) for page in read_pdf(read_html(item.path))
        ]
    return []


def get_pdf_image(file_path: str) -> PILImage.Image:
    return PILImage.fromarray(read_pdf(file_path)[0])


def get_html_image(file_path: str) -> PILImage.Image:
    return PILImage.fromarray(read_pdf(read_html(file_path))[0])


def generate_thumbnail(
    image_path,
    thumbnail_path,
    max_dimensions=(4096, 4096),
    max_file_size=20 * 1024 * 1024,
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
        return False

    with PILImage.open(image_path) as img:
        # Check if the image is overly large based on dimensions
        if (
            img.size[0] <= max_dimensions[0]
            and img.size[1] <= max_dimensions[1]
            and file_size <= max_file_size
        ):
            return False

        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        # Generate thumbnail
        img.thumbnail(max_dimensions, PILImage.Resampling.LANCZOS)
        img.save(thumbnail_path, "JPEG")

    return True
