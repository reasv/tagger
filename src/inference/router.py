import logging
from typing import Any, Dict, List

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from src.inference.impl.clip import ClipModel
from src.inference.impl.ocr import DoctrModel
from src.inference.impl.sentence_transformers import SentenceTransformersModel
from src.inference.impl.wd_tagger import WDTagger
from src.inference.impl.whisper import FasterWhisperModel
from src.inference.manager import InferenceModel, ModelManager
from src.inference.registry import ModelRegistry
from src.inference.utils import encode_output_response, parse_input_request

logger = logging.getLogger(__name__)

registry = ModelRegistry(user_folder="config/inference")
registry.register_model(WDTagger)
registry.register_model(DoctrModel)
registry.register_model(SentenceTransformersModel)
registry.register_model(FasterWhisperModel)
registry.register_model(ClipModel)

router = APIRouter(
    prefix="/inference",
    tags=["inference"],
    responses={404: {"description": "Not found"}},
)


@router.post("/predict/{group}/{inference_id}")
def predict(
    group: str,
    inference_id: str,
    cache_key: str = Query(...),
    lru_size: int = Query(...),
    ttl_seconds: int = Query(...),
    data: str = Form(...),  # The JSON data as a string
    files: List[UploadFile] = File([]),  # The binary files
):
    inputs = parse_input_request(data, files)
    logger.debug(
        f"Processing {len(inputs)} ({len(files)} files) inputs for model {group}/{inference_id}"
    )
    # Instantiate the model (without loading)
    model_instance: InferenceModel = registry.get_model_instance(
        group, inference_id
    )

    # Load the model with cache key, LRU size, and long TTL to avoid unloading during prediction
    model: InferenceModel = ModelManager().load_model(
        f"{group}/{inference_id}", model_instance, cache_key, lru_size, -1
    )

    try:
        # Perform prediction
        outputs: List[bytes | dict | list | str] = list(model.predict(inputs))
    except Exception as e:
        logger.error(f"Prediction failed for model {inference_id}: {e}")
        raise HTTPException(status_code=500, detail="Prediction failed")
    finally:
        # Update the model's TTL after the prediction is made
        ModelManager().load_model(
            f"{group}/{inference_id}",
            model_instance,
            cache_key,
            lru_size,
            ttl_seconds,
        )

    return encode_output_response(outputs)


@router.put("/load/{group}/{inference_id}")
def load_model(
    group: str,
    inference_id: str,
    cache_key: str,
    lru_size: int,
    ttl_seconds: int,
) -> Dict[str, str]:
    try:
        model_instance: InferenceModel = registry.get_model_instance(
            group, inference_id
        )
        ModelManager().load_model(
            f"{group}/{inference_id}",
            model_instance,
            cache_key,
            lru_size,
            ttl_seconds,
        )
        return {"status": "loaded"}
    except Exception as e:
        logger.error(f"Failed to load model {inference_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to load model")


@router.put("/unload/{group}/{inference_id}")
def unload_model(
    group: str,
    inference_id: str,
    cache_key: str,
) -> Dict[str, str]:
    ModelManager().unload_model(cache_key, f"{group}/{inference_id}")
    return {"status": "unloaded"}


@router.delete("/cache/{cache_key}")
def clear_cache(cache_key: str) -> Dict[str, str]:
    ModelManager().clear_cache(cache_key)
    return {"status": "cache cleared"}


@router.get("/cache")
async def list_loaded_models() -> Dict[str, List[str]]:
    return ModelManager().list_loaded_models()


@router.get("/metadata")
async def list_model_metadata() -> Dict[str, Dict[str, Any]]:
    return registry.list_inference_ids()


@router.post("/check_ttl")
async def check_ttl() -> Dict[str, str]:
    ModelManager().check_ttl_expired()
    return {"status": "ttl checked"}
