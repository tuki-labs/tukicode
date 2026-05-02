# 🏗️ Arquitectura de TukiCode

Este documento detalla la estructura interna, las funciones de cada archivo y cómo interactúan los componentes para dar vida al agente TukiCode.

## 📁 Estructura del Proyecto

### 🔹 Raíz del Proyecto
- **[tuki.py](file:///d:/software/tukicode/tuki.py)**: Punto de entrada principal (CLI). Gestiona los comandos de nivel superior (`chat`, `config`, `history`, `models`) usando la librería `typer`.
- **[config.py](file:///d:/software/tukicode/config.py)**: Sistema de configuración centralizado. Carga y guarda preferencias desde `tukicode.toml`.
- **[agent_icon.py](file:///d:/software/tukicode/agent_icon.py)**: Contiene el arte ASCII y la lógica de animación para la mascota "Tuki".

### 🔹 Core del Agente (`/agent`)
El motor de inteligencia reside aquí:
- **[loop.py](file:///d:/software/tukicode/agent/loop.py)**: El corazón del agente. Implementa el patrón **ReAct** (Reason + Act). Orquestra el envío de prompts al LLM, la ejecución de herramientas y la actualización del contexto.
- **[context.py](file:///d:/software/tukicode/agent/context.py)**: Gestiona la memoria a corto plazo de la conversación. Incluye lógica para conteo de tokens y compresión de historial si se excede la ventana de contexto.
- **[parser.py](file:///d:/software/tukicode/agent/parser.py)**: Analiza las respuestas del modelo para identificar cuándo el agente quiere usar una herramienta o dar una respuesta final.
- **[ollama_client.py](file:///d:/software/tukicode/agent/ollama_client.py)**: Cliente para interactuar con la API local de Ollama.
- **[openrouter_client.py](file:///d:/software/tukicode/agent/openrouter_client.py)**: Cliente para interactuar con la API de OpenRouter (modelos en la nube).

### 🔹 Interfaz de Usuario (`/ui`)
La UI ha sido modernizada a una arquitectura basada en eventos usando **Textual**:
- **[app.py](file:///d:/software/tukicode/ui/app.py)**: **La App Principal**. Define el layout, los estilos CSS y maneja los eventos del usuario. Reemplaza a los antiguos `layout.py` e `input.py`.
- **[display.py](file:///d:/software/tukicode/ui/display.py)**: Capa de abstracción que actúa como puente entre el `AgentLoop` y la `TukiApp`. Asegura que los mensajes se rendericen correctamente en el hilo adecuado.

---

## 🎨 Diseño Visual y UI (Textual)

TukiCode utiliza **Textual** (un framework TUI basado en Python) para ofrecer una experiencia premium y estable.

### Componentes del Layout
1.  **Header**: Muestra el título de la app y un reloj.
2.  **Left Panel (#left-panel)**: Un widget `Static` que muestra la animación de Tuki usando un intervalo de actualización.
3.  **Chat Log (#chat-log)**: Un widget `RichLog` que gestiona el historial de mensajes con scroll fluido y renderizado de Markdown.
4.  **Thinking Panel (#thinking-panel)**: Un panel que aparece/desaparece dinámicamente sobre la barra de entrada para mostrar el razonamiento del agente.
5.  **Input Bar (#input-bar)**: Campo de texto donde el usuario escribe.
6.  **Status Bar (#status-bar)**: Muestra información en tiempo real (Modelo, Tokens, Nivel de Riesgo).

### ¿Cómo funciona la comunicación?
Debido a que Textual maneja su propio bucle de eventos, el agente (`AgentLoop`) corre en tareas asíncronas separadas. Para actualizar la UI sin causar errores de hilos:
1.  El agente llama a `display.show_message()`.
2.  `display.py` usa `app.call_later(app.add_message, ...)` para programar la actualización en el hilo principal de la UI.
3.  Esto garantiza que la terminal no se rompa y que la interfaz sea reactiva.

---

## 🛠️ Cómo seguir extendiendo la UI

### 1. Agregar nuevos Widgets
Para añadir elementos (ej. una lista de archivos abiertos), edita el método `compose()` en `ui/app.py`:
```python
def compose(self) -> ComposeResult:
    yield Header()
    with Horizontal():
        yield Static(id="mi-nuevo-panel") # Agrega esto
        yield RichLog(id="chat-log")
    # ...
```

### 2. Cambiar Estilos (CSS)
Textual usa una sintaxis similar a CSS3. Puedes modificar `TukiApp.CSS` en `ui/app.py` para cambiar colores, bordes o visibilidad:
```css
#mi-nuevo-panel {
    background: #111;
    border: solid #333;
    width: 20;
}
```

### 3. Agregar Comandos de Barra
Nuevos comandos como `/stats` se deben agregar en `TukiApp.handle_command()`:
```python
elif text == "/stats":
    self.add_message("system", f"Tokens usados: {self.context.token_count}")
```

---

## 🛠️ Tecnologías Clave
- **[Textual](https://github.com/Textualize/textual)**: Framework principal para el layout y manejo de eventos TUI.
- **[Rich](https://github.com/Textualize/rich)**: Para el renderizado de Markdown, colores ANSI y tablas.
- **[Typer](https://typer.tiangolo.com/)**: Para la creación de la interfaz CLI de comandos.
- **[SQLite](https://www.sqlite.org/)**: Para el almacenamiento persistente del historial.
