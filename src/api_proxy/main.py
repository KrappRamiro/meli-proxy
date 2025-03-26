import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_fastapi_instrumentator import Instrumentator

from .config_loader import ConfigLoader, ConfigWatcher
from .rate_limiter import RateLimiter
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

    # === Integración con Prometheus
    # See https://github.com/trallnag/prometheus-fastapi-instrumentator?tab=readme-ov-file#exposing-endpoint
    instrumentator.expose(app, include_in_schema=True)

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

# Integración con Prometheus
# see https://github.com/trallnag/prometheus-fastapi-instrumentator
instrumentator = Instrumentator().instrument(app)


@app.api_route("/proxy/{path:path}")
# Acá devolvemos Any, porque no sabemos que puede llegar a devolver la API de MeLi
# Para más info sobre Request, ver https://fastapi.tiangolo.com/advanced/using-request-directly/#using-the-request-directly
async def proxy_request(request: Request, path: str) -> Any:
    """
    Proxy the request to the MercadoLibre API
    """

    # Why this is here? There are some cases where request.client can be None, to see when,
    # read https://github.com/encode/starlette/discussions/2244#discussioncomment-6694242
    if request.client is None:
        raise HTTPException(
            detail="""For some reason, request.client was None.
            That only happens on this case: https://github.com/encode/starlette/discussions/2244#discussioncomment-6694242 .
            Maybe uvicorn is listening on a UNIX socket, and its misconfigured as detailed in the github starlette discussion.  """,
            status_code=500,
        )
    # We need the client_ip to rate-limit later,
    client_ip = request.client.host
    # La url a la que le vamos a hacer la request
    target_url = f"{os.environ['MELI_API_URL']}/{path}"
    logger.info("Handling a request to %s , with client IP %s", target_url, client_ip)

    # Verificar rate limiting usando app.state,
    # explicación de app.state en https://stackoverflow.com/a/71298949/15965186
    if not await request.app.state.rate_limiter.is_allowed(client_ip, path):
        # Raise a HTTP 429 Too Many Requests
        logger.warning("The request to %s , with client IP %s , has rate-limited", target_url, client_ip)
        raise HTTPException(status_code=429, detail="Too Many Requests (Rate limit exceeded)")

    # Intentamos hacer la request
    try:
        async with httpx.AsyncClient() as client:
            # Send request
            response = await client.request(
                method=request.method,
                url=target_url,
                # TODO: Ver por qué, si yo uso los headers de la request, Heroku (probablemente de mockapi) me falla con un error de certificados SSL
                headers={
                    "Accept": "*",
                },
                # Acá convertimos reponse.query_params a un diccionario ya que FastAPI espera que params sea un dict.
                params=dict(request.query_params),
                content=await request.body(),
            )

        logger.debug("Response received - Status: %s", response.status_code)

        # Una vez terminada la request de httpx, retornamos la response que nos dió la API de MeLi
        # Devolvemos la Response cruda, manteniendo los headers originales
        return Response(
            content=response.content,
            status_code=response.status_code,
            # Acá convertimos reponse.headers a un diccionario ya que FastAPI espera que headers sea un dict.
            headers=dict(response.headers),
        )

    except httpx.HTTPError as e:
        logger.error("HTTP error: %s", str(e))
        # Use `from e` to comply with https://pylint.readthedocs.io/en/latest/user_guide/messages/warning/raise-missing-from.html
        raise HTTPException(status_code=500, detail="Error connecting to upstream service") from e

    except Exception as e:
        logger.exception("Internal server error")
        # Use `from e` to comply with https://pylint.readthedocs.io/en/latest/user_guide/messages/warning/raise-missing-from.html
        raise HTTPException(status_code=500, detail="Internal Server Error") from e
