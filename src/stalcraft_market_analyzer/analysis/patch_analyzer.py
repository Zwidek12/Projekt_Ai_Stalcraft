import json
import os
from pydantic import BaseModel, Field
from typing import List
from openai import OpenAI

# 1. Definiujemy struktury danych, jakich wymagamy od AI
class PatchAnalysisResult(BaseModel):
    """Schemat JSONa, który musi zwrócić LLM."""
    patch_version: str = Field(description="Wersja patcha, np. '1.0.4'")
    buffed_items: List[str] = Field(description="Lista ID przedmiotów, które zostały wzmocnione")
    nerfed_items: List[str] = Field(description="Lista ID przedmiotów, które zostały osłabione")
    neutral_items: List[str] = Field(description="Lista ID przedmiotów ze zmianami neutralnymi")
    confidence: float = Field(description="Pewność modelu od 0.0 do 1.0", ge=0.0, le=1.0)
    raw_summary: str = Field(description="Krótkie podsumowanie zmian w jednym zdaniu")

# 2. Główna funkcja integracyjna
def analyze_patch_notes(text: str, provider: str = "openai") -> PatchAnalysisResult:
    """
    Analizuje tekst patch notes i zwraca ustrukturyzowany obiekt.
    """
    system_prompt = """
    Jesteś analitykiem rynku i mechaniki w grze Stalcraft. 
    Przeanalizuj poniższe patch notes i sklasyfikuj przedmioty jako buffed (wzmocnione), 
    nerfed (osłabione) lub neutral (zmienione neutralnie).
    Musisz zwrócić DOKŁADNIE obiekt JSON i nic więcej.
    """

    if provider == "openai":
        # Pobieramy klucz API ze zmiennych środowiskowych systemu
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("⚠️ Brak klucza OPENAI_API_KEY. Zwracam dane mockowane.")
            return _get_mock_analysis()
            
        client = OpenAI(api_key=api_key)
        
        # Prawdziwe strzelanie do OpenAI z wymuszeniem formatu JSON (pydantic) zostanie tu dodane
        pass

    elif provider == "ollama":
        print("❌ Adapter Ollama jeszcze niezaimplementowany.")
        raise NotImplementedError
    
    return _get_mock_analysis()

def _get_mock_analysis() -> PatchAnalysisResult:
    """Tymczasowa funkcja zwracająca sztuczne dane, gdy nie mamy jeszcze podpiętego klucza."""
    return PatchAnalysisResult(
        patch_version="Patch 1.5.2",
        buffed_items=["wpn_ak74u"],
        nerfed_items=["med_medkit", "med_bandage"],
        neutral_items=["art_sun"],
        confidence=0.85,
        raw_summary="Zwiększono obrażenia AK-74U i zmniejszono leczenie podstawowych apteczek."
    )

if __name__ == "__main__":
    # Szybki test lokalny
    dummy_text = "Dzisiaj zwiększamy obrażenia w AK-74U, ale apteczki będą leczyć słabiej."
    wynik = analyze_patch_notes(dummy_text)
    print(f"Wynik analizy: \n{wynik.model_dump_json(indent=2)}")