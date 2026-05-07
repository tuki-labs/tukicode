# TukiCode

![TukiCode Logo](./media/tukilogo.png)

**TukiCode** es un agente de programacion CLI de codigo abierto construido en Python. Funciona localmente con Ollama o en la nube con OpenRouter, Gemini y Anthropic. Cuenta con una arquitectura completamente asincrona diseñada para un alto rendimiento y capacidad de respuesta.

---

## Novedades

- **Arquitectura Asincrona** - Todos los clientes LLM utilizan metodos asincronos nativos (httpx, asyncio) para ejecucion no bloqueante y transmision mas rapida.
- **Separacion MVC** - La logica de negocio, el cambio de modelos de IA y las interacciones con la base de datos estan aisladas en un Controlador dedicado, completamente separado de la capa de interfaz de usuario.
- **Planificador Estructurado** - El planificador del agente impone estrictamente salidas estructuradas en JSON para generar planes de implementacion precisos paso a paso.
- **TUI Completa** - Interfaz a pantalla completa (Textual) con panel de chat, explorador de archivos y Consola en Vivo.
- **Terminal Interactiva (PTY)** - Pseudo-terminal real para servidores de larga duracion y comandos interactivos.
- **Soporte Multi-Proveedor** - Ollama (local), OpenRouter, Gemini, Anthropic.

---

## Instalacion

### Windows (PowerShell)

```powershell
iwr https://tukicode.site/api/install.ps1 | iex
```

Descarga `tuki.exe` a `%LOCALAPPDATA%\TukiCode\bin` y lo añade a tu PATH.

### macOS

```bash
curl -fsSL https://tukicode.site/api/install.sh | bash
```

**Primera ejecucion en macOS:** Si ves una advertencia de seguridad, ejecuta:
```bash
xattr -d com.apple.quarantine ~/.local/bin/tuki
```

### Linux

```bash
curl -fsSL https://tukicode.site/api/install.sh | bash
```

Tanto macOS como Linux instalan `tuki` en `~/.local/bin` y actualizan tu perfil de shell automaticamente.

### Desde el codigo fuente (Cualquier SO)

```bash
git clone https://github.com/sb4ss/tukicode.git
cd tukicode
pip install -r requirements.txt
python tuki.py chat
```

---

## Inicio Rapido

```bash
# 1. Configura tu proveedor de IA
tuki config --setup

# 2. Inicia el agente
tuki chat
```

---

## Configuracion

```bash
tuki config --setup     # Asistente interactivo
tuki config             # Mostrar configuracion actual
tuki config --model     # Cambiar solo el modelo
```

### Modelos gratuitos recomendados (via OpenRouter)

| Modelo | Notas |
|---|---|
| `tencent/hy3-preview:free` | Recomendado: mejor uso de herramientas en nivel gratuito |
| `moonshotai/kimi-k2.5` | Razonamiento rapido |
| `deepseek/deepseek-chat-v3.2` | Tareas de programacion solidas |

> TukiCode requiere modelos con **soporte nativo para llamadas a herramientas** para la funcionalidad completa del agente.

---

## Comandos de Chat

| Comando | Descripcion |
|---|---|
| `/help` | Lista todos los comandos disponibles |
| `/setup` | Abre el asistente de configuracion dentro del chat |
| `/model` | Cambia el modelo de IA |
| `/autonomy [low\|medium\|high]` | Controla la frecuencia con la que el agente pide confirmacion |
| `/risk [low\|medium\|high]` | Ajusta la sensibilidad de riesgo para la ejecucion de herramientas |
| `/copy [n]` | Copia el bloque de codigo `n` de la ultima respuesta |
| `/history` | Muestra las sesiones recientes |
| `/clear` | Limpia el registro del chat |
| `/exit` | Sale y guarda la sesion |

### Atajos de teclado

| Atajo | Accion |
|---|---|
| `Ctrl+S` | Parada de emergencia: detiene la ejecucion actual del agente |
| `Ctrl+B` | Alterna el panel de Consola en Vivo |
| `Ctrl+L` | Limpia el registro del chat |

---

## Requisitos

- Python 3.10+
- Uno de los siguientes:
  - **Ollama** ejecutandose localmente (`ollama serve`)
  - Clave API para **OpenRouter**, **Gemini**, o **Anthropic**

---

## Resumen de Arquitectura

```
tuki.py              <- Punto de entrada CLI (Typer)
core/
  controller.py      <- TukiController (Logica de negocio y gestion de LLM)
agent/
  loop.py            <- Bucle de razonamiento ReAct (Asincrono)
  planner.py         <- Planificador de salida JSON estructurada
  executor.py        <- Ejecutor de planes asincrono paso a paso
  clients...         <- Clientes API asincronos
tools/
  registry.py        <- Registro y despacho de herramientas
ui/
  app.py             <- Aplicacion TUI Textual
config.py            <- Gestor de configuracion TOML
```

Para documentacion tecnica mas profunda, consulta [ARCHITECTURE.md](./ARCHITECTURE.md).
