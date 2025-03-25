import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .config_loader import ConfigLoader, ConfigWatcher
from .rate_limiter import RateLimiter
from .rules import parse_rules
from .utils import setup_redis_client

# TODO: Reemplazar carga de variables de entorno por https://evarify.readthedocs.io/


@asynccontextmanager
# redefined-outer-name is disabled because this function is from the FastApi docs
# # pylint: disable=redefined-outer-name
async def lifespan(app: FastAPI):
    """
    Qué es esto de acá?
    Esto de acá maneja el lifespan de nuestra app

    Esto está en reemplazo de @app.on_event("startup/shutdown"),
    app.on_event fue deprecado, y ahora se usa un context manager llamado @asynccontextmanager

    Lo que hace esto de acá es bastante sencillo:
    - La lógica de startup va antes del yield
    - La lógica de cleanup va después del yield

    Para más información, ver https://fastapi.tiangolo.com/advanced/events/#lifespan
    """
    # ===================================== #
    # === Lógica de startup inicia acá ==== #

    # === Uso de app.state
    # En esa sección cargamos cosas en app.state, esto es para poder reusarlas en cada endpoint
    # sin la necesidad de usar variables globales
    # Para más info, ver https://stackoverflow.com/q/76322463/15965186

    # === Redis
    # Based on https://www.reddit.com/r/FastAPI/comments/1e67aug/how_to_use_redis/
    app.state.redis_client = await setup_redis_client()

    # === Config
    # Obtenemos la config del archivo .YAML
    config = ConfigLoader(os.environ["CONFIG_FILE_PATH"])
    # Guardamos la config en el state
    app.state.config = config

    # === Rate Limiter
    # Guardamos la configuración del rate limiter en base a las reglas de configuración
    app.state.rate_limiter = RateLimiter(app.state.redis_client, config.rules)

    # Iniciar watcher para cambios en config.yaml
    app.state.watcher = ConfigWatcher(config.config_path, config.reload)
    app.state.watcher.start()

    # === Lógica de startup termina acá === #
    # ===================================== #

    yield

    # ===================================== #
    # === Lógica de cleanup inicia acá ==== #
    await app.state.redis_client.close()
    app.state.watcher.stop()

    # === Lógica de cleanup termina acá === #
    # ===================================== #


# Inicializamos nuestra instancia de FastAPI
app = FastAPI(lifespan=lifespan, title="Meli Proxy")

# See https://stackoverflow.com/a/77007723/15965186
logger = logging.getLogger("uvicorn.error")


# Acá devolvemos Any, porque no sabemos que puede llegar a devolver la API de MeLi
@app.api_route("/{path:path}")
async def proxy_request(request: Request, path: str) -> Any:
    """
    Proxy the request to the MercadoLibre API
    """

    # We need the client_ip to rate-limit later
    if request.client is None:
        raise HTTPException(
            detail="For some reason, request.client was None",
            status_code=400,
        )
    client_ip = request.client.host
    target_url = f"{os.environ['MELI_API_URL']}/{path}"

    # Verificar rate limiting usando app.state,
    # explicación de app.state en https://stackoverflow.com/a/71298949/15965186
    logger.info("Handling a request to %s , with client IP %s", target_url, client_ip)
    if not await request.app.state.rate_limiter.is_allowed(client_ip, path):
        # Raise a HTTP 429 Too Many Requests
        logger.warning("The request to %s , with client IP %s , has rate-limited", target_url, client_ip)
        raise HTTPException(status_code=429, detail="Too Many Requests (Rate limit exceeded)")

    try:
        async with httpx.AsyncClient() as client:
            # Send request
            response = await client.request(
                method=request.method,
                url=target_url,
                headers={
                    # TODO: lograr overridear request.headers
                    # **dict(request.headers),
                    "User-Agent": "(httpx/async, krappramiro.jpg@gmail.com)",
                    "Accept": "application/json",
                },
                params=dict(request.query_params),
                content=await request.body(),
            )

        # Una vez terminada la request de httpx, retornamos la response que nos dió la API de MeLi
        return JSONResponse(
            content=response.json(),
            status_code=response.status_code,
            headers=dict(response.headers),
        )

    except Exception as e:
        logger.error("🚨 Backend Proxy Error: %s", e)
        # Use `from e` to comply with https://pylint.readthedocs.io/en/latest/user_guide/messages/warning/raise-missing-from.html
        raise HTTPException(
            detail=f"Internal Proxy Error: {e}",
            status_code=500,
        ) from e
