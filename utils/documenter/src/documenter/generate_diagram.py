from utilities.model import (
    Edition, Manuscript, ManuscriptHoldingInstitution,
    ManuscriptPreservationStatus, Text, TextForm, TextSourceType,
    TextSourceSubtype,
)
from sqlalchemy_data_model_visualizer import generate_data_model_diagram
import os

def main():
    models = [
        Text, TextForm, TextSourceType, TextSourceSubtype,
        Manuscript, ManuscriptPreservationStatus,
        ManuscriptHoldingInstitution, Edition,
    ]
    output_file_name = '../../data/hagiographies_model'
    try:
        generate_data_model_diagram(models, output_file_name)
        os.remove(output_file_name)
    except FileNotFoundError:
        print("Ignored xdg-open error")

if __name__ == "__main__":
    main()
