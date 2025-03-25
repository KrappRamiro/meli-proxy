"""
rate_limiter.py
Este archivo implementa el Rate Limiter del proxy
"""

import redis

from .rules import IPAndPathRule, IPRule, PathRule, Rule


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
        if isinstance(rule, IPRule):
            return f"limit:ip:{ip}"
        if isinstance(rule, PathRule):
            return f"limit:path:{path}"
        if isinstance(rule, IPAndPathRule):
            return f"limit:ip_path:{ip}:{path}"
        # Si todos los isinstance de antes fallaron,
        # significa que no es ninguna regla que _generate_key reconozca
        raise ValueError(f"Tipo de regla no soportado: {type(rule)}")

    async def is_allowed(self, ip: str, path: str) -> bool:
        """
        Verifica, en base a una lista de reglas, si la petición rompe alguna de ellas.

        Para esto, pide la IP y el PATH

        Esta función es async porque nuestra conexión a redis lo es

        TODO: cambiar para que no pida solamente IP y PATH, sino que pida una lista (o diccionario) de elementos a validar. Para eso, hay que cambiar tambien _generate_key
        """
        for rule in self.rules:
            # Genera un string con la key a usar en redis
            print(f"La regla es {rule}")
            key = self._generate_key(rule, ip, path)

            # requests_amount va a comenzar a tener la cantidad de peticiones que se hicieron teniendo en cuenta la IP y el Path
            # Si la key no existe en Redis, la inicializa con valor 1
            # Si en cambio si existe, incrementa el valor de la key
            requests_amount = await self.redis.incr(key)

            # Esto solamente pasa cuando la key es nueva
            if requests_amount == 1:
                # Le da un tiempo de expiración (TTL) a la key
                await self.redis.expire(key, rule.window)
                return True

            # Si la cantidad de requests superaron al límite permitido, retorna Falso, lo cual significa que esa request fue rate-limiteada!
            if requests_amount > rule.limit:
                return False
