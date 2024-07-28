import sqlite3
from typing import Iterable, List, Sequence, Text, Tuple

import faster_whisper
import numpy as np
import torch
from faster_whisper.transcribe import Segment, TranscriptionInfo

from src.data_extractors.ai.text_embed import TextEmbedder
from src.data_extractors.data_loaders.audio import load_audio
from src.data_extractors.extraction_jobs import run_extraction_job
from src.data_extractors.models import WhisperSTTModel
from src.db.extracted_text import insert_extracted_text
from src.db.setters import upsert_setter
from src.db.text_embeddings import add_text_embedding
from src.types import ItemWithPath


def run_whisper_extractor_job(
    conn: sqlite3.Connection, model_opts: WhisperSTTModel
):
    """
    Run a job that processes items in the database using the given batch inference function and item extractor.
    """

    device = "cpu"
    if torch.cuda.is_available():
        device = "cuda"

    whisper_model = faster_whisper.WhisperModel(
        model_opts.model_repo(), device=device, compute_type="float16"
    )
    if model_opts.batch_size() > 1:
        whisper_model = faster_whisper.BatchedInferencePipeline(
            model=whisper_model, batch_size=model_opts.batch_size()
        )

    threshold = model_opts.threshold()

    text_embedder = TextEmbedder()

    embedding_setter_id = upsert_setter(
        conn, text_embedder.model_type(), text_embedder.model_name()
    )

    def get_media_paths(item: ItemWithPath) -> Sequence[np.ndarray]:
        if item.type.startswith("video"):
            audio = load_audio(item.path)
            return [audio] if audio is not None else []
        elif item.type.startswith("audio"):
            audio = load_audio(item.path)
            return [audio] if audio is not None else []
        return []

    def process_batch(batch: Sequence[np.ndarray]) -> List[
        Tuple[
            Iterable[Segment],
            TranscriptionInfo,
        ]
    ]:
        outputs: List[
            Tuple[
                Iterable[Segment],
                TranscriptionInfo,
            ]
        ] = []
        for audio in batch:
            outputs.append(whisper_model.transcribe(audio=audio))
        return outputs

    def handle_item_result(
        log_id: int,
        item: ItemWithPath,
        _: Sequence[np.ndarray],
        outputs: Sequence[
            Tuple[
                Iterable[Segment],
                TranscriptionInfo,
            ]
        ],
    ):
        for segments, info in outputs:
            segment_list = [
                (segment.text, segment.avg_logprob)
                for segment in segments
                if not threshold or segment.avg_logprob > threshold
            ]
            text_segments = [segment[0] for segment in segment_list]
            merged_text = "\n".join(text_segments)

            merged_text = merged_text.strip()
            if len(merged_text) < 3:
                continue

            text_embeddings = text_embedder.get_text_embeddings([merged_text])

            assert isinstance(
                text_embeddings, list
            ), "embeddings should be lists of floats"
            text_embedding = text_embeddings[0]

            average_log_prob = (
                sum(segment[1] for segment in segment_list) / len(segment_list)
                if len(segment_list) > 0
                else None
            )
            text_id = insert_extracted_text(
                conn,
                item.sha256,
                log_id,
                text=merged_text,
                language=info.language,
                language_confidence=info.language_probability,
                confidence=average_log_prob,
            )
            add_text_embedding(
                conn,
                text_id,
                embedding_setter_id,
                text_embedding,
            )

    return run_extraction_job(
        conn,
        model_opts,
        get_media_paths,
        process_batch,
        handle_item_result,
    )
