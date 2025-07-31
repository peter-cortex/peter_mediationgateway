from huggingface_hub import login, hf_hub_download
import openwakeword

openwakeword.utils.download_models(["alexa"])


model_path = hf_hub_download(
            repo_id="Alevxis/wakewordcova",
            filename="Cova.tflite",
            use_auth_token=False,
        )
print(f"model_path : {model_path}")