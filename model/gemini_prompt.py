from enum import Enum
from pydantic import BaseModel

class Animal(Enum):
    KANGAROO = "kangaroo"
    KOALA = "koala"
    WOMBAT = "wombat"
    PLATYPUS = "platypus"
    CROCODILE = "crocodile"
    COCKATOO = "cockatoo"
    OWL = "owl"
    FROG = "frog"
    SNAKE = "snake"
    TASMANIAN_DEVIL = "tasmanian_devil"

class Classification(BaseModel):
    animal: Animal
