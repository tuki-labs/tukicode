from setuptools import setup, find_packages

setup(
    name="tukicode",
    version="1.0.0",
    packages=find_packages(),
    py_modules=["tuki", "config", "agent_icon"],
    install_requires=[
        "ollama",
        "rich",
        "typer[all]",
        "prompt-toolkit"
    ],
    entry_points={
        "console_scripts": [
            "tuki=tuki:app",
        ],
    },
)
