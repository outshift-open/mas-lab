# Interrupt a bad session, persist it, inspect. Same as:
#   mas-ctl control $SESSION pause --reason bad-session persist --label bad --auto-stop inspect checkpoints
pause --reason bad-session
persist --label bad --auto-stop
inspect
checkpoints
