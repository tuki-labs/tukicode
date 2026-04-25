# Integración OpenClaw (Ejemplo)

Esta es una integración de ejemplo que muestra cómo extender TukiCode con nuevas herramientas.

## ¿Qué hace?
Simula la conexión con un gestor de correos electrónicos. Agrega tres herramientas:
- `read_emails(limit)`
- `send_email(to, subject, body)`
- `search_emails(query)`

## ¿Cómo activarla?
En tu archivo `tukicode.toml`, cambia `enabled` a `true`:

```toml
[integrations.openclaw]
enabled = true
```

*Nota: esta es una integración de prueba, no envía ni lee correos reales.*
