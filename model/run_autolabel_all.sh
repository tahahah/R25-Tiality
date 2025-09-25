#!/bin/bash
set -e

# Get the directory of the script to ensure we run from the right place
cd "$(dirname "${BASH_SOURCE[0]}")"

CLASSES=(
    "cockatoo"
    "croc"
    "frog"
    "kangaroo"
    "koala"
    "platypus"
    "tasmanian devil"
    "wombat"
)

for class in "${CLASSES[@]}"; do
    echo "--- Processing class: $class ---"
    prompt="$class"
    if [ "$class" == "croc" ]; then
        prompt="crocodile"
    fi
    uv run python autolabel_boxes.py --class "$class" --prompt "$prompt"
done

echo "--- All classes processed successfully. ---"
