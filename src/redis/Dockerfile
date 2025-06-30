FROM redis:7.2-alpine

# Crear directorio para configuración
RUN mkdir -p /usr/local/etc/redis

# Copiar archivo de configuración personalizado si existe
COPY redis.conf /usr/local/etc/redis/redis.conf

# Exponer el puerto por defecto de Redis
EXPOSE 6379

# Comando para ejecutar Redis con la configuración personalizada
CMD ["redis-server", "/usr/local/etc/redis/redis.conf"]