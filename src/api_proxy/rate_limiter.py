"""
rate_limiter.py
Este archivo implementa el Rate Limiter del proxy
"""

import logging
from pprint import pformat

import redis

from .utils import matches_pattern

from .rules import IPPathRule, IPRule, PathRule, Rule

# See https://stackoverflow.com/a/77007723/15965186
logger = logging.getLogger("uvicorn.error")


class RateLimiter:
    def __init__(self, redis_client: redis.Redis, rules: list[Rule]):
        self.redis = redis_client
        self.load_rules(rules)

    def load_rules(self, rules: list[Rule]):
        """
        Loads the rules into the RateLimiter
        This is made like this so Rate Limiter can support new rules being added while the program is executed
        """
        self.rules = rules

    def _generate_key(self, rule: Rule, ip: str, path: str) -> str:
        """
        Genera la key para guardar en Redis según el tipo de regla.

        TODO: Hacer que no solamente pida ip y path, sino que en realidad pida una lista o diccionario de elementos a validar

        TODO: hacer un diagrama con Mermaid del flujo de cómo funciona todo esto
        """
        if not isinstance(rule, Rule):
            # significa que no es ninguna regla que _generate_key reconozca
            logger.error(
                "En el RateLimiter, en _generate_key , se obtuvo una variable rule con el tipo %s, pero este tipo no es una instancia de Rule",
                type(rule),
            )
            raise ValueError(f"El tipo no es una instancia de Rule: {type(rule)}")

        if isinstance(rule, IPRule):
            key = f"limit:by_ip:{ip}"
        elif isinstance(rule, PathRule):
            key = f"limit:by_path:{path}"
        elif isinstance(rule, IPPathRule):
            key = f"limit:by_ip_path:{ip}:{path}"
        else:
            # significa que no es ninguna regla que _generate_key reconozca
            logger.error(
                "En el RateLimiter, _generate_key obtuvo una rule con tipo %s, pero esta Rule no es soportada", type(rule)
            )
            raise ValueError(f"Tipo de regla no soportado: {type(rule)}")

        logger.info("Generada la key: %s", key)
        return key

    async def is_allowed(self, ip: str, path: str) -> bool:
        """
        Verifica, en base a una lista de reglas, si la petición rompe alguna de ellas.

        Para esto, pide la IP y el PATH

        Esta función es async porque nuestra conexión a redis lo es

        TODO: cambiar para que no pida solamente IP y PATH, sino que pida una lista (o diccionario) de elementos a validar. Para eso, hay que cambiar tambien _generate_key
        """

        logger.debug("INICIA IS ALLOWED")
        logger.debug("Our rules are: %s", pformat(self.rules))
        for rule in self.rules:
            # Genera un string con la key a usar en redis

            logger.debug("Checkeando la rule %s", rule)

            # ================ #
            # MATCHEO DE LA RULE

            if isinstance(rule, IPRule):
                logger.debug("Es instancia de IPRule!")
                if ip == rule.ip:
                    logger.debug("Match con IP!")
                else:
                    logger.debug("No matcheo!")
                    continue
            elif isinstance(rule, PathRule):
                logger.debug("Es instancia de PathRule!")
                if matches_pattern(path, rule.pattern):
                    logger.debug("Match con PATH!")
                else:
                    logger.debug("No matcheo!")
                    continue
            elif isinstance(rule, IPPathRule):
                logger.debug("Es instancia de IPPathRule!")
                if ip == rule.ip and matches_pattern(path, rule.pattern):
                    logger.debug("Match con PATH e IP!")
                else:
                    logger.debug("No matcheo!")
                    continue
            else:
                logger.debug("No matcheo ninguna instancia con la regla %s, siguiente regla!", rule)
                continue

            # ================ #

            logger.debug("Esta rule tiene un límite de %s", rule.limit)
            key = self._generate_key(rule, ip, path)

            # requests_amount va a comenzar a tener la cantidad de peticiones que se hicieron teniendo en cuenta la IP y el Path
            # Si la key no existe en Redis, la inicializa con valor 1
            # Si en cambio si existe, incrementa el valor de la key
            requests_amount = await self.redis.incr(key)
            logger.debug("La key tenía %s peticiones", requests_amount)

            # Esto solamente pasa cuando la key es nueva
            if requests_amount == 1:
                logger.debug("Esto significa que esa key la acabamos de crear!")
                # Le da un tiempo de expiración (TTL) a la key
                await self.redis.expire(key, rule.window)

            # Si la cantidad de requests superaron al límite permitido, retorna Falso, lo cual significa que esa request fue rate-limiteada!
            if requests_amount > rule.limit:
                logger.debug("Esto significa que la key debe ser rate-limiteada")
                return False
        return True
