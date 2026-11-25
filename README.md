# Otto

An importable framework for Markdown-first organisations. Its first release is being built; the framework is empty for now, with a command-line skeleton that will be filled in over subsequent development.

Install by git tag once a release exists, for example:

```sh
pip install "banodoco-otto @ git+https://github.com/banodoco/otto@v0.1.0"
```

Use `otto --help` to see the planned commands and `otto --version` to see the installed version. Currently, `otto list` produces no output on standard output; if there is no `otto.toml` in the current directory, it reports that on standard error. The other commands are placeholders.

Licence: MIT.
