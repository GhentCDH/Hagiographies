from utilities.model import (
    Archdiocese, Author, AuthorMilieu, DatingConfidence, Diocese, Edition,
    EditionEdition, EditionManuscript, Institution, Location, Manuscript,
    ManuscriptHoldingInstitution, ManuscriptPreservationStatus, Repertory,
    RepertoryLink, Text, TextForm, TextSourceType, TextSourceSubtype,
)
from sqlalchemy_data_model_visualizer import generate_data_model_diagram
import os

def main():
    models = [
        Text, TextForm, TextSourceType, TextSourceSubtype,
        DatingConfidence, Author, AuthorMilieu,
        Location, Archdiocese, Diocese, Institution,
        Manuscript, ManuscriptPreservationStatus,
        ManuscriptHoldingInstitution, Edition,
        EditionManuscript, EditionEdition,
        Repertory, RepertoryLink,
    ]
    output_file_name = '../../data/hagiographies_model'
    try:
        generate_data_model_diagram(models, output_file_name)
        os.remove(output_file_name)
    except FileNotFoundError:
        print("Ignored xdg-open error")

if __name__ == "__main__":
    main()
