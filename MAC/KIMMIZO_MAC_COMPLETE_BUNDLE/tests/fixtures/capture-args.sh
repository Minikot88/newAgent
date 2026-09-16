#!/bin/zsh
for argument in "$@"; do
  print -r -- "$argument"
done
