"""demo3: prove, straight from the installed package, that both guards default
to 100 -- the same number, guarding two loops that fail in opposite ways.

Run:  python demo3_defaults_from_package.py
"""
import inspect

import haystack
from haystack import Pipeline
from haystack.components.agents import Agent

print(f"haystack-ai version: {haystack.__version__}")

pipe_default = inspect.signature(Pipeline.__init__).parameters["max_runs_per_component"].default
agent_default = inspect.signature(Agent.__init__).parameters["max_agent_steps"].default

print(f"Pipeline.max_runs_per_component default: {pipe_default}")
print(f"Agent.max_agent_steps default:           {agent_default}")
print(f"same default value? {pipe_default == agent_default}")
