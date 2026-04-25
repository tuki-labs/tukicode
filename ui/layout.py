from prompt_toolkit.application import Application
from prompt_toolkit.layout.containers import HSplit, VSplit, Window, WindowAlign
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.widgets import TextArea, Frame
from prompt_toolkit.formatted_text import ANSI, to_formatted_text
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.lexers import Lexer
from rich.markdown import Markdown
from rich.console import Console
from rich.panel import Panel
import asyncio
from agent_icon import TukiAnimation
from ui.display import TukiDisplay
from agent.loop import AgentLoop
import webbrowser


class AnsiLexer(Lexer):
    def lex_document(self, document):
        def get_line(lineno):
            return to_formatted_text(ANSI(document.lines[lineno]))
        return get_line

class TukiApp:
    def __init__(self, config, client, registry, context, session_id=None):
        self.config = config
        self.client = client
        self.registry = registry
        self.context = context
        self.session_id = session_id
        self.anim = TukiAnimation(start_thread=False)
        
        # Dedicated console for ANSI capture
        self.ui_console = Console(force_terminal=True, color_system="truecolor")
        
        # UI State
        self._history_ansi = ""
        self._current_stream = ""
        self._is_streaming = False
        self._exiting = False
        self.session_title = None
        
        # Command History
        self.cmd_history = []
        self.cmd_index = -1
        self.current_typing = ""
        
        # Display with callback
        self.display = TukiDisplay(on_output=self.append_text)
        self.agent_loop = AgentLoop(config, client, registry, context, self.display)
        
        # UI Elements
        self.output_area = TextArea(
            lexer=AnsiLexer(),
            read_only=True,
            scrollbar=True,
            wrap_lines=True,
            focusable=True
        )
        
        self.input_field = TextArea(
            height=1,
            prompt=" [You] > ",
            multiline=False,
            wrap_lines=False,
            style="class:input-field"
        )
        
        # Mascot, Banner & Tokens
        self.mascot_control = FormattedTextControl(text=self._get_mascot_text)
        self.banner_control = FormattedTextControl(text=self._get_banner_text)
        self.token_bar_control = FormattedTextControl(text=self._get_token_bar_text)

        # Layout
        self.layout = Layout(
            HSplit([
                VSplit([
                    Window(content=self.mascot_control, height=9, width=40),
                    Window(content=self.banner_control, height=9, align=WindowAlign.CENTER),
                ], height=9, style="class:header"),
                
                Frame(
                    self.output_area, 
                    title=" TukiCode Session ", 
                    style="class:chat-frame"
                ),
                
                Window(content=self.token_bar_control, height=1, align=WindowAlign.RIGHT, style="class:token-bar"),
                Window(height=1, char="─", style="class:separator"),
                self.input_field,
            ]),
            focused_element=self.input_field
        )

        # Key Bindings
        self.kb = KeyBindings()

        @self.kb.add("c-c")
        def _(event):
            event.app.exit()

        @self.kb.add("c-s")
        def _(event):
            if self._is_streaming:
                self.display.should_stop = True

        @self.kb.add("enter")
        def _(event):
            self._handle_submit()


        #List recent commands in chat session
        @self.kb.add("up")
        def _(event):
            if self.cmd_history and self.cmd_index < len(self.cmd_history) - 1:
                if self.cmd_index == -1:
                    self.current_typing = self.input_field.text
                self.cmd_index += 1
                self.input_field.text = self.cmd_history[len(self.cmd_history) - 1 - self.cmd_index]
    
        @self.kb.add("down")
        def _(event):
            if self.cmd_index >= 0:
                self.cmd_index -= 1
                if self.cmd_index == -1:
                    self.input_field.text = self.current_typing
                else:
                    self.input_field.text = self.cmd_history[len(self.cmd_history) - 1 - self.cmd_index]

        # Styles
        self.style = Style.from_dict({
            "chat-frame": "#555555",
            "frame.border": "#333333",
            "frame.title": "bold #a0e025",
            "input-field": "bold #ffffff",
            "prompt": "bold #a0e025",
            "separator": "#222222",
        })

        self.application = Application(
            layout=self.layout,
            key_bindings=self.kb,
            style=self.style,
            full_screen=True,
            refresh_interval=0.1,
            mouse_support=True
        )

        self.agent_loop.start_session()
        self._append_to_history("\n [bold green]Welcome to TukiCode![/bold green] Type your message below.\n")

    def _get_token_bar_text(self):
        used = self.context.token_count
        total = self.config.model.context_window
        percentage = (used / total) * 100 if total > 0 else 0
        
        bar_width = 30
        filled = int((percentage / 100) * bar_width)
        empty = bar_width - filled
        
        bar = "█" * filled + "░" * empty
        
        color = "green"
        if percentage > 75:
            color = "yellow"
        if percentage > 90:
            color = "red"
            
        text = f" Tokens: [{color}]{used}/{total}[/{color}] [{color}]{bar}[/{color}] {percentage:.1f}% "
        
        with self.ui_console.capture() as capture:
            self.ui_console.print(text, end="")
        return ANSI(capture.get())



    # This is the render before the ui starts. It renders the last session context.
    # the messages are loaded from the json file based on the session_id.
    def render_loaded_context(self):
        if len(self.context.messages) > 1:
            self._history_ansi = ""
            self._append_to_history("\n [bold green]Restored Session Context[/bold green]\n")
            for msg in self.context.messages:
                if msg["role"] == "user":
                    self._append_to_history(f"\n[bold cyan]You:[/bold cyan] {msg['content']}\n")
                elif msg["role"] == "assistant":
                    size = self.application.renderer.output.get_size()
                    self.ui_console.width = max(size.columns - 4, 10)
                    with self.ui_console.capture() as capture:
                        self.ui_console.print("\n[bold cyan]TukiCode:[/bold cyan]")
                        self.ui_console.print(Panel(
                            Markdown(msg['content']), 
                            border_style="cyan", 
                            title="Assistant Response",
                            expand=True
                        ))
                    self._history_ansi += capture.get()
            self._refresh_display(auto_scroll=True)

    #This is the render of the mascot. It renders the ascii art of the mascot.
    def _get_mascot_text(self):
        frame = self.anim.get_current_frame()
        return ANSI("\n".join(frame))


    #This is the render of the banner. It renders the model, risk, and exit instructions.
    def _get_banner_text(self):
        text = (f"\n[bold blue]TukiCode v1.0.0[/bold blue]\n"
                f"  Model: [cyan]{self.config.model.name}[/cyan]\n"
                f"  Risk: [yellow]{self.config.agent.risk_level}[/yellow]\n"
                f"  [dim]Ctrl+S: Stop | Ctrl+C: Exit[/dim]\n"
                f"  [dim] Type /exit to Exit or /clear to Clear[/dim]")
        
        with self.ui_console.capture() as capture:
            self.ui_console.print(text, end="")
        return ANSI(capture.get())

    def _append_to_history(self, text, is_markup=True):
        if is_markup:
            size = self.application.renderer.output.get_size()
            self.ui_console.width = max(size.columns - 6, 30)
            with self.ui_console.capture() as capture:
                self.ui_console.print(text, end="")
            ansi = capture.get()
        else:
            ansi = text
            
        self._history_ansi += ansi
        self._refresh_display(auto_scroll=True)

    def _refresh_display(self, auto_scroll=True):
        content = self._history_ansi
        
        if self._is_streaming and self._current_stream:
            size = self.application.renderer.output.get_size()
            self.ui_console.width = size.columns - 6
            with self.ui_console.capture() as capture:
                self.ui_console.print("\n[bold cyan]TukiCode:[/bold cyan]")
                self.ui_console.print(Markdown(self._current_stream))
            content += capture.get()

        # Check if cursor is at the end before updating
        was_at_bottom = self.output_area.buffer.cursor_position == len(self.output_area.text)
        
        self.output_area.text = content
        
        if auto_scroll or was_at_bottom:
            self.output_area.buffer.cursor_position = len(content)
        
        self.application.invalidate()

    def append_text(self, text, is_markup=False, is_final=False, final_text=None, is_start=False):
        # 1. Handle Turn End
        if is_final:
            self._is_streaming = False
            self._current_stream = ""
            
            # Render the final panel
            size = self.application.renderer.output.get_size()
            self.ui_console.width = size.columns - 4
            with self.ui_console.capture() as capture:
                self.ui_console.print("\n[bold cyan]TukiCode:[/bold cyan]")
                self.ui_console.print(Panel(
                    Markdown(final_text), 
                    border_style="cyan", 
                    title="Assistant Response",
                    expand=True
                ))
            
            self._history_ansi += capture.get()
            self._refresh_display(auto_scroll=True)
            return

        # 2. Handle Stream Start
        if is_start:
            self._is_streaming = True
            self._current_stream = ""
            return

        # 3. Handle Content
        if self._is_streaming:
            self._current_stream += text
            # Debounce rendering for smoothness
            if len(self._current_stream) % 5 == 0:
                self._refresh_display(auto_scroll=True)
        else:
            # System messages or tool results
            self._append_to_history(text, is_markup=is_markup)

    # Commands and prompts handler
    def _handle_submit(self):
        text = self.input_field.text.strip()
        
        if self._exiting:
            self.session_title = text if text else None
            self.application.exit()
            return

        if not text:
            return

        if not self.cmd_history or self.cmd_history[-1] != text:
            self.cmd_history.append(text)
        self.cmd_index = -1
        self.current_typing = ""
        self.input_field.text = ""
        
        if text == "/exit":
            self._exiting = True
            self.input_field.prompt = " [Session Name (Optional)] > "
            self._append_to_history("\n[bold yellow]Enter a name for this session (or press Enter for default):[/bold yellow]\n")
            self._refresh_display(auto_scroll=True)
            return
            
        
            
        if text == "/clear":
            self._history_ansi = ""
            self.output_area.text = ""
            self._refresh_display(auto_scroll=True)
            self._append_to_history("\n [bold green]Screen cleared![/bold green] Type your message below.\n")
            return

        if text == "/help":
            self._append_to_history(f"\n[bold green]Available commands:[/bold green]\n")
            self._append_to_history(f"\n[bold green]/exit [/bold green][italic]- Exit TukiCode[/italic]\n")
            self._append_to_history(f"\n[bold green]/copy [/bold green][italic]- Copy assistant's code Block from response[/italic]\n")
            self._append_to_history(f"\n[bold green]/clear [/bold green][italic]- Clear the screen[/italic]\n")
            self._append_to_history(f"\n[bold green]/current_session [/bold green][italic]- Show current session ID[/italic]\n")
            self._append_to_history(f"\n[bold green]/site [/bold green][italic]- Open TukiCode website[/italic]\n")
            self._append_to_history(f"\n[dim]Or press Ctrl+C to exit and tuki --help from terminal.[/dim]\n")
            self._append_to_history(f"\n[bold yellow]Thank you for using TukiCode![/bold yellow]\n")
            self._refresh_display(auto_scroll=True)
            return


        if text == "/site":
            #open browser
            webbrowser.open("https://github.com/sb4ss")
            self._append_to_history(f"\n[bold purple]Opening TukiCode website...[/bold purple]\n")
            self._refresh_display(auto_scroll=True)
            return

        if text == "/current_session":
            self._append_to_history(f"\n[dim]Session ID:[/dim] {self.session_id}\n")
            self._refresh_display(auto_scroll=True)
            return 

        if text.startswith("/copy"):
            import re
            import pyperclip
            
            parts = text.split()
            target_idx = 1
            if len(parts) > 1 and parts[1].isdigit():
                target_idx = int(parts[1])
                
            last_assistant_msg = None
            for msg in reversed(self.context.messages):
                if msg["role"] == "assistant":
                    last_assistant_msg = msg["content"]
                    break
                    
            if not last_assistant_msg:
                self._append_to_history("\n[bold red]No AI responses found to copy from.[/bold red]\n")
                self._refresh_display(auto_scroll=True)
                return

            code_blocks = re.findall(r"```[a-zA-Z]*\n(.*?)```", last_assistant_msg, re.DOTALL)
            
            if not code_blocks:
                self._append_to_history("\n[bold red]No code blocks found in the last AI response.[/bold red]\n")
                self._refresh_display(auto_scroll=True)
                return
                
            if target_idx > len(code_blocks) or target_idx < 1:
                self._append_to_history(f"\n[bold red]Code block index {target_idx} out of range. (Found {len(code_blocks)})[/bold red]\n")
                self._refresh_display(auto_scroll=True)
                return
                
            code_to_copy = code_blocks[target_idx - 1].strip()
            try:
                pyperclip.copy(code_to_copy)
                self._append_to_history(f"\n[bold green]Code block {target_idx} copied to clipboard![/bold green]\n")
            except Exception as e:
                self._append_to_history(f"\n[bold red]Failed to copy to clipboard: {e}[/bold red]\n")
                
            self._refresh_display(auto_scroll=True)
            return

        if text.startswith("/"):
            self._append_to_history(f"\n[bold red]Unknown command:[/bold red] {text}\n")
            self._append_to_history(f"\n[bold green]Use /exit to Exit, /clear to Clear, or /copy to copy code.[/bold green]\n")
            return


            
        self._append_to_history(f"\n[bold cyan]You:[/bold cyan] {text}\n")
        asyncio.create_task(self._run_agent(text))

    async def _run_agent(self, user_msg):
        try:
            await self.agent_loop.run_turn(user_msg)
        except Exception        as e:
            self._append_to_history(f"\n[bold red]Error:[/bold red] {str(e)}\n")

    def run(self):
        self.application.run()
