# Break on the first web_search tool result, then on every calc tool call.
# Commands run at the breakpoint; checkpoints stay in memory.

break tool_result web_search if first
commands
  checkpoint
  info checkpoints
  info session
  info working_memory
  continue
end

break tool_call calc
commands
  checkpoint
  info checkpoints
  info session
  info working_memory
  continue
end
