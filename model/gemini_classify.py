import os
import random
import logging
import asyncio
from dotenv import load_dotenv
from google import genai
from google.genai import types
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from gemini_prompt import Classification

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

REFERENCE_IMAGE_DIR = "/Users/taha/Repos/R25-Tiality/model/gemini_inputs"
DATASET_DIR = "/Users/taha/Downloads/ECE4191 Dataset"

REFERENCE_IMAGES = {
    "kangaroo": os.path.join(REFERENCE_IMAGE_DIR, "kangaroo.png"),
    "koala": os.path.join(REFERENCE_IMAGE_DIR, "koala.png"),
    "wombat": os.path.join(REFERENCE_IMAGE_DIR, "wombat.png"),
    "platypus": os.path.join(REFERENCE_IMAGE_DIR, "platypus.png"),
    "crocodile": os.path.join(REFERENCE_IMAGE_DIR, "crocodile.png"),
    "cockatoo": os.path.join(REFERENCE_IMAGE_DIR, "cockatoo.png"),
    "owl": os.path.join(REFERENCE_IMAGE_DIR, "owl.png"),
    "frog": os.path.join(REFERENCE_IMAGE_DIR, "frog.png"),
    "snake": os.path.join(REFERENCE_IMAGE_DIR, "snake.png"),
    "tasmanian_devil": os.path.join(REFERENCE_IMAGE_DIR, "tasmanian_devil.png"),
}

def get_random_images(num_images=3):
    all_images = []
    for root, _, files in os.walk(DATASET_DIR):
        for file in files:
            if file.lower().endswith(".jpg"):
                all_images.append(os.path.join(root, file))
    return random.sample(all_images, min(num_images, len(all_images)))

async def classify_image(image_path):
    prompt_parts = [
        "system: Your job is to classify the animal in the image into one of the following 10 classes: kangaroo, koala, wombat, platypus, crocodile, cockatoo, owl, frog, snake, tasmanian_devil. You will be given one reference image for each class. You must respond with only a single JSON object matching the provided schema, like `{\"animal\": \"wombat\"}`.",
    ]

    for animal, path in REFERENCE_IMAGES.items():
        prompt_parts.append(f"user: {animal}")
        with open(path, "rb") as f:
            prompt_parts.append(types.Part.from_bytes(data=f.read(), mime_type="image/png"))

    prompt_parts.append("user: Given the reference images I've provided you for all 10 classes, what class does the the following image belong to?")
    with open(image_path, "rb") as f:
        prompt_parts.append(types.Part.from_bytes(data=f.read(), mime_type="image/jpeg"))

    logging.info(f"Classifying image: {image_path}")
    response = await client.aio.models.generate_content(
        model="gemini-2.5-pro",
        contents=prompt_parts,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Classification,
            thinking_config=types.ThinkingConfig(
                thinking_budget=128  # Lower budget for faster classification (range: 128-32768)
            )
        ),
    )

    logging.info(f"Received response: {response.text}")
    return response.parsed

async def main():
    sample_images = get_random_images(3)
    semaphore = asyncio.Semaphore(2)  # Limit to 2 concurrent requests

    async def classify_with_semaphore(image_path):
        async with semaphore:
            return await classify_image(image_path)

    tasks = [classify_with_semaphore(image_path) for image_path in sample_images]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    axes = axes.flatten()

    for i, (image_path, result) in enumerate(zip(sample_images, results)):
        ax = axes[i]
        img = mpimg.imread(image_path)
        ax.imshow(img)
        ax.axis('off')

        if isinstance(result, Exception):
            label = "Error"
            logging.error(f"Error classifying {image_path}: {result}")
        elif result:
            label = result.animal.value
        else:
            label = "Unclassified"
        
        ax.set_title(f"Predicted: {label}")

    # Hide any unused subplots
    for j in range(len(sample_images), len(axes)):
        axes[j].axis('off')

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    asyncio.run(main())
