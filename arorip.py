from flask import Flask, render_template, request, jsonify
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
from zipfile import ZipFile, BadZipFile
from pathlib import Path
import requests
from flask import Flask, request, jsonify

# Flask app setup
app = Flask(__name__)

# Credentials
username = "yaramis-m"
password = "yara7643"

# Opslaglocatie
save_path = Path("c:/temp/AroDocOnline")
os.makedirs(save_path, exist_ok=True)


# Route voor de webpagina
@app.route("/autobom")
def autobom_page():
    return render_template("autobom.html")


# API route voor het verwerken van de downloadactie
@app.route("/download", methods=["POST"])
def download_action():
    try:
        # Lees de JSON-gegevens van de frontend
        data = request.get_json()
        if not data:
            return jsonify({"log": "Geen gegevens ontvangen."}), 400

        variants = data.get("variants", "")
        extract_zip = data.get("extract", False)

        if not variants.strip():
            return jsonify({"log": "Geen varianten opgegeven."})

        variant_list = [v.strip() for v in variants.splitlines() if v.strip()]

        log = "Inloggen op ARO DocOnline...\n"

        # Selenium WebDriver in headless mode
        options = webdriver.FirefoxOptions()
        options.add_argument("--headless")
        driver = webdriver.Firefox(options=options)

        driver.get("https://docs.arotechnologies.com/index.php")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "nomlogin"))
        ).send_keys(username)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "motpass"))
        ).send_keys(password)
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='submit']"))
        ).click()

        log += "Succesvol ingelogd op ARO DocOnline.\n"

        download_path = Path.home() / "Downloads"

        for variant in variant_list:
            log += f"Bezig met variant: {variant}\n"
            driver.get(
                f"https://docs.arotechnologies.com/menu.php?numvariante={variant}"
            )

            # Wachten op de frame en switchen
            WebDriverWait(driver, 10).until(
                EC.frame_to_be_available_and_switch_to_it((By.NAME, "tableau"))
            )

            # Wachten op de downloadknop en klikken
            download_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@value='Download']"))
            )
            download_button.click()

            zip_path = download_path / f"_{variant}.zip"
            extract_path = save_path / variant

            # Wachten tot het bestand is gedownload
            WebDriverWait(driver, 30).until(
                lambda d: zip_path.exists() and zip_path.stat().st_size > 0
            )

            # ZIP-bestand uitpakken alleen als de checkbox is aangevinkt
            if extract_zip:
                try:
                    with ZipFile(zip_path, "r") as zObject:
                        zObject.extractall(path=extract_path)
                    os.remove(zip_path)
                    log += f"Documenten voor variant {variant} gedownload en uitgepakt naar {extract_path}.\n"
                except BadZipFile:
                    log += f"Fout: Bestand voor variant {variant} is geen geldig ZIP-bestand.\n"
                    os.remove(zip_path)
            else:
                log += (
                    f"ZIP-bestand voor variant {variant} gedownload naar {zip_path}.\n"
                )

        driver.quit()
        log += "Alle documenten zijn gedownload.\n"

        return jsonify({"log": log})

    except Exception as e:
        return jsonify({"log": f"Fout: {str(e)}"}), 500



import os

if __name__ == "__main__":
    # Voorkom dat Flask's development server draait in productie
    if os.environ.get("FLASK_ENV") != "production":
        port = int(os.environ.get("PORT", 8090))  # Gebruik de dynamische poort voor Railway
        app.run(host="0.0.0.0", port=port, debug=True)

    
