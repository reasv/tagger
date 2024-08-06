import sqlite3
from typing import List

from src.db import get_item_id
from src.types import ExtractedText, ExtractedTextStats


def insert_extracted_text(
    conn: sqlite3.Connection,
    item_sha256: str,
    index: int,
    log_id: int,
    text: str,
    language: str | None,
    language_confidence: float | None,
    confidence: float | None,
) -> int:
    """
    Insert extracted text into the database
    """
    text = text.strip()
    if len(text) < 3:
        return -1

    item_id = get_item_id(conn, item_sha256)
    assert item_id is not None, f"Item with SHA256 {item_sha256} not found"

    confidence = round(float(confidence), 4) if confidence is not None else None
    language_confidence = (
        round(float(language_confidence), 4)
        if language_confidence is not None
        else None
    )
    cursor = conn.cursor()

    sql = """
    INSERT INTO extracted_text (idx, item_id, log_id, setter_id, language, language_confidence, confidence, text)
    SELECT ?, ?, ?, logs.setter_id, ?, ?, ?, ?
    FROM data_extraction_log AS logs
    WHERE logs.id = ?
    """
    cursor.execute(
        sql,
        (
            index,
            item_id,
            log_id,
            language,
            language_confidence,
            confidence,
            text,
            log_id,
        ),
    )
    assert cursor.lastrowid is not None, "Last row ID is None"
    return cursor.lastrowid


def get_extracted_text_for_item(
    conn: sqlite3.Connection, item_sha256: str
) -> List[ExtractedText]:
    """
    Get all extracted text for an item
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            items.sha256,
            setters.type,
            setters.name,
            language,
            text,
            confidence,
            language_confidence
        FROM extracted_text
        JOIN setters AS setters 
        ON extracted_text.setter_id = setters.id
        JOIN items ON extracted_text.item_id = items.id
        WHERE items.sha256 = ?
    """,
        (item_sha256,),
    )
    rows = cursor.fetchall()

    # Map each row to an ExtractedText dataclass instance
    extracted_texts = [
        ExtractedText(
            item_sha256=row[0],
            model_type=row[1],
            setter_name=row[2],
            language=row[3],
            text=row[4],
            confidence=row[5],
            language_confidence=row[6],
        )
        for row in rows
    ]
    return extracted_texts


def get_text_stats(conn: sqlite3.Connection) -> ExtractedTextStats:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT DISTINCT language
        FROM extracted_text
        WHERE language IS NOT NULL
        """
    )
    rows = cursor.fetchall()
    languages = [row[0] for row in rows]
    # Get the minimum overall language confidence and the minimum confidence

    cursor.execute(
        """
        SELECT MIN(language_confidence), MIN(confidence)
        FROM extracted_text
        """
    )
    row = cursor.fetchone()
    language_confidence = row[0]
    confidence = row[1]
    return ExtractedTextStats(
        languages=languages,
        lowest_language_confidence=language_confidence,
        lowest_confidence=confidence,
    )
