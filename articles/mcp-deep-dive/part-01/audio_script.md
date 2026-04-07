# Audio Script

Hey, welcome back. I'm Praveen Kumar and today we're talking about Introduction to Model Context Protocol (MCP).

As engineers, we often face a messy web of custom connectors when linking AI to data. MCP, an open standard by Anthropic, fixes this by providing a universal interface. It reduces integration complexity from O(N times M) to a standardized O(N plus M) model.

Technically, it's built on JSON-RPC 2.0 and uses three core primitives: Resources, Tools, and Prompts. Whether using local STDIO or remote HTTP, the protocol establishes a session where the server shares its capabilities with the client. This allows AI models to dynamically discover and fetch data at runtime, abstracting away the complex authentication and fetching logic.

The takeaway is simple: MCP decouples your models from your data sources. This makes your AI systems much easier to scale, manage, and swap between different providers or tools.

Follow me on LinkedIn so you don't miss Part 2. See you there.