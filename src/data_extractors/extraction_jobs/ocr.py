import sqlite3
from typing import List, Sequence, Tuple

import numpy as np
import torch
from chromadb.api import ClientAPI
from doctr.models import ocr_predictor

from src.data_extractors.data_loaders.images import item_image_loader_numpy
from src.data_extractors.extraction_jobs import run_extraction_job
from src.data_extractors.models import OCRModel
from src.data_extractors.text_embeddings import (
    add_item_text,
    get_text_embedding_model,
)
from src.db.extracted_text import insert_extracted_text
from src.db.text_embeddings import add_text_embedding
from src.types import ItemWithPath


def run_ocr_extractor_job(
    conn: sqlite3.Connection, cdb: ClientAPI, model_opt: OCRModel
):
    """
    Run a job that processes items in the database using the given batch inference function and item extractor.
    """

    doctr_model = ocr_predictor(
        det_arch=model_opt.detection_model(),
        reco_arch=model_opt.recognition_model(),
        detect_language=True,
        pretrained=True,
    )
    if torch.cuda.is_available():
        doctr_model = doctr_model.cuda().half()
    text_embedding_model = get_text_embedding_model()

    threshold = model_opt.threshold()

    def process_batch(
        batch: Sequence[np.ndarray],
    ) -> List[
        Tuple[str, List[float], dict[str, str | float | None], List[float]]
    ]:
        result = doctr_model(batch)
        files_texts: List[str] = []
        languages: List[dict[str, str | float | None]] = []
        word_confidences: List[List[float]] = []
        for page in result.pages:
            file_text = ""
            languages.append(page.language)
            page_word_confidences = []
            for block in page.blocks:
                for line in block.lines:
                    for word in line.words:
                        if threshold and word.confidence < threshold:
                            continue
                        file_text += word.value + " "
                        page_word_confidences.append(word.confidence)
                    file_text += "\n"
                file_text += "\n"
            files_texts.append(file_text)
            word_confidences.append(page_word_confidences)

        assert isinstance(files_texts, list), "files_texts should be a list."
        assert all(
            isinstance(text, str) for text in files_texts
        ), "All elements in files_texts should be strings."

        embeddings = text_embedding_model.encode(files_texts)
        assert isinstance(
            embeddings, np.ndarray
        ), "embeddings should be numpy arrays"
        embeddings_lists = embeddings.tolist()
        return list(
            zip(files_texts, embeddings_lists, languages, word_confidences)
        )

    def handle_item_result(
        log_id: int,
        item: ItemWithPath,
        _: Sequence[np.ndarray],
        outputs: Sequence[
            Tuple[str, List[float], dict[str, str | float | None], List[float]]
        ],
    ):
        # Deduplicate the text from the OCR output
        string_set = set()
        for extracted_string, embedding, language, word_confidences in outputs:
            cleaned_string = extracted_string.lower().strip()
            if len(cleaned_string) < 3:
                continue
            if cleaned_string in string_set:
                continue
            string_set.add(cleaned_string)
            min_confidence = min(word_confidences)
            assert (
                isinstance(language["confidence"], float)
                or language["confidence"] is None
            ), "Language confidence should be a float or None"

            assert (
                isinstance(language["value"], str) or language["value"] is None
            ), "Language value should be a string or None"

            text_id = insert_extracted_text(
                conn,
                item.sha256,
                log_id,
                text=cleaned_string,
                language=language["value"],
                language_confidence=language["confidence"],
                confidence=min_confidence,
            )
            add_text_embedding(
                conn,
                text_id,
                embedding,
            )
            add_item_text(
                cdb=cdb,
                item=item,
                model=model_opt,
                language=language["value"] or "unknown",
                text=cleaned_string,
            )

    return run_extraction_job(
        conn,
        model_opt,
        item_image_loader_numpy,
        process_batch,
        handle_item_result,
    )
