# TukiCode

<div align="center">
  <img src="./media/tukilogo.png" alt="TukiCode Logo" width="200"/>
  <h3>Stable Release v1.3.1</h3>
</div>

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

## Modos de Operacion

TukiCode tiene tres modos de operacion distintos, seleccionables mediante tabs en la TUI. Cada uno enruta tu entrada a traves de un pipeline diferente en `core/controller.py`.

| Modo | Tab | Pipeline | Ideal para |
|---|---|---|---|
| **Chat** | Chat Mode | `AgentLoop.run_turn()` directo | Preguntas rapidas, arreglos aislados, explicaciones |
| **Plan** | Plan Mode | `Planner` → muestra pasos → **pide confirmacion** → `Executor` | Tareas de varios pasos donde quieres revisar antes de ejecutar |
| **Build** | Build Mode | `Planner` → **muestra pasos** → `Executor` inmediatamente | Generacion autonoma de proyectos completos sin interrupciones |

### Chat Mode

El agente recibe tu mensaje y entra directamente al loop ReAct. Piensa, llama herramientas, observa los resultados y repite hasta producir una `FinalResponse`. No se genera un plan estructurado: el modelo decide cada accion en tiempo real.

### Plan Mode

1. Tu mensaje se envia a `Planner.generate_plan()`, que llama al LLM y devuelve un array JSON de pasos atomicos.
2. El plan se muestra en pantalla y el agente **se pausa**, preguntando `"¿Deseas ejecutar este plan? (y/n)"`.
3. Si confirmas, `Executor.execute_plan()` ejecuta cada paso secuencialmente via `AgentLoop.run_turn()`, con reintentos y cambio de modelo en caso de fallo.

### Build Mode

1. Si existe un plan pendiente en `planner_state.json`, la ejecucion se reanuda desde el ultimo paso pendiente.
2. Si no hay plan previo, `Planner.generate_plan()` se invoca automaticamente. El plan generado se **muestra** en el chat antes de comenzar.
3. `Executor.execute_plan()` arranca inmediatamente, **sin pedir confirmacion**.

> **¿Cuando usar Build vs Plan?** Usa **Plan** cuando quieras revisar y aprobar la estrategia primero. Usa **Build** cuando confies en el agente para construir de forma autonoma y prefieras velocidad.

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
