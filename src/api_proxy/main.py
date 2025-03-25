import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from .config_loader import ConfigLoader, ConfigWatcher
from .rate_limiter import RateLimiter

# TODO: Reemplazar carga de variables de entorno por https://evarify.readthedocs.io/


async def setup_redis_client():
    """
    Based on https://www.reddit.com/r/FastAPI/comments/1e67aug/how_to_use_redis/
    """
    redis_client = Redis(
        host=os.environ["REDIS_HOST"],
        port=os.environ["REDIS_PORT"],
        password=os.environ["REDIS_PASSWORD"],
        decode_responses=True,
    )
    try:
        await redis_client.ping()
        # TODO: Change with logger implementation
        print("Redis is connected")
    except Exception as e:
        # TODO Replace this generic exception class with a more specific one
        raise Exception(f"Redis is not connected: {e}")
    return redis_client


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
    config = ConfigLoader(os.environ["RULES_YAML_CONFIG_PATH"])
    # Guardamos la config en el state
    app.state.config = config

    # === Rate Limiter
    # Guardamos la configuración del rate limiter en base a las reglas de configuración

    app.state.rate_limiter = RateLimiter(app.state.redis_client, config.rules)

    # Iniciar watcher para cambios en rules.yaml
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
app = FastAPI(lifespan=lifespan)


@app.api_route("/{path:path}")
async def proxy_request(request: Request, path: str):
    """
    Proxy the request to the MercadoLibre API
    """

    # We need the client_ip to rate-limit later
    client_ip = request.client.host

    # Verificar rate limiting usando app.state,
    # explicación de app.state en https://stackoverflow.com/a/71298949/15965186
    if not await request.app.state.rate_limiter.is_allowed(client_ip, request.url.path):
        # Raise a HTTP 429 Too Many Requests
        raise HTTPException(status_code=429, detail="Too Many Requests (Rate limit exceeded)")

    # Reenviar request al backend
    async with httpx.AsyncClient() as client:
        backend_url = f"{os.environ["MELI_API_URL"]}/{path}"

        print(f"Request a {backend_url}")
        # Hacemos una request a la API de MeLi con toda la data necesaria
        response = await client.request(
            method=request.method,
            url=backend_url,
            headers=dict(request.headers),
            params=dict(request.query_params),
            content=await request.body(),
        )
        print(response.status_code)
        print(response.text)

    # Una vez terminada la request de httpx, retornamos la response que nos dió la API de MeLi

    return JSONResponse(
        content=response.json(),
        status_code=response.status_code,
        headers=dict(response.headers),
    )
