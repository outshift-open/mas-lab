# Compliance tool installation

This directory is optional and isolated from MAS Lab runtime dependencies.

## A2A TCK

The official TCK is not a PyPI release. The supported setup is:

```bash
task --dir library-ioa/compliance/a2a install
task --dir library-ioa/compliance/a2a install-tck
```

With the deterministic compliance SUT running, execute all requirement levels
across every declared transport:

```bash
task --dir library-ioa/compliance/a2a tck-positive
```

## Official A2A CLI

The official CLI is the Go binary from `a2aproject/a2a-cli`, not the unrelated
PyPI distribution named `a2a-cli`:

```bash
go install github.com/a2aproject/a2a-cli@v0.3.0
mv "$(go env GOPATH)/bin/a2a-cli" "$(go env GOPATH)/bin/a2a"
```

On macOS, Homebrew is also supported:

```bash
brew tap a2aproject/a2a-cli https://github.com/a2aproject/a2a-cli
brew install a2a
```

## MCP conformance

The official MCP framework is an npm package:

```bash
npx --yes @modelcontextprotocol/conformance --help
npx @modelcontextprotocol/conformance server \
  --url http://127.0.0.1:9001/mcp
```
