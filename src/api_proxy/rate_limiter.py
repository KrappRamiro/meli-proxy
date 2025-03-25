"""
Implementa el mecanismo de rate limiting usando Redis como backend.
"""

import logging
from pprint import pformat

import redis

from .rules import Rule

logger = logging.getLogger("uvicorn.error")


class RateLimiter:
    """
    Servicio principal que aplica las reglas de rate limiting.

    Atributos:
        redis (redis.Redis): Conexión a Redis
        rules (List[Rule]): Reglas activas para evaluación
    """

    def __init__(self, redis_client: redis.Redis, rules: list[Rule]):
        """
        Inicializa el rate limiter.

        Args:
            redis_client (redis.Redis): Cliente Redis configurado
            rules (list[Rule]): Lista de reglas a aplicar
        """
        self.redis = redis_client
        self.rules = rules

    def load_rules(self, rules: list[Rule]):
        """
        Actualiza las reglas activas en tiempo de ejecución.

        Args:
            rules (list[Rule]): Nueva lista de reglas
        """
        self.rules = rules

    async def is_allowed(self, ip: str, path: str) -> bool:
        """
        Evalúa todas las reglas para determinar si se permite la solicitud.

        Args:
            ip (str): IP del cliente
            path (str): Ruta accedida

        Returns:
            bool: True si se permite, False si se excede algún límite

        """
        logger.debug("Iniciando evaluación de rate limiting para IP: %s, Path: %s", ip, path)
        for rule in self.rules:
            logger.debug("Evaluando regla: %s", pformat(rule))

            if not rule.matches(ip, path):
                logger.debug("La regla no aplica - omitiendo")
                continue

            key = rule.generate_key(ip, path)
            logger.debug("Key generada en Redis: %s", key)

            try:
                current = await self.redis.incr(key)
                logger.debug("Valor actual del contador: %s", current)

                if current == 1:
                    logger.debug("Primera solicitud - configurando TTL a %s segundos", rule.window)
                    await self.redis.expire(key, rule.window)

                if current > rule.limit:
                    logger.warning("Límite excedido para %s", key)
                    return False
            except redis.RedisError as e:
                logger.error("Error de Redis: %s - Permitiendo solicitudes por fallo del Redis", str(e))
                return True  # Fail-open

        logger.debug("Todas las reglas fueron evaluadas")
        return True
