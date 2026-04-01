from utilities.model import (
    Place, Institution, Author, Typology, ManuscriptType, Milieu,
    ChurchEntity, ManuscriptIdentifier, DatingCentury, ImageAvailability,
    VernacularRegion, ProvenanceGeneral, Text, Manuscript, Image,
    ExternalResource, EditionExternalResource,
    ManuscriptRelation, Edition, EditionManuscript, ManuscriptText
)
from utilities.db import engine
from sqlalchemy_data_model_visualizer import generate_data_model_diagram
import os

def main():
    models = [
        Place, Institution, Author, Typology, ManuscriptType, Milieu,
        ChurchEntity, ManuscriptIdentifier, DatingCentury, ImageAvailability,
        VernacularRegion, ProvenanceGeneral, Text, Manuscript, Image,
        ExternalResource, EditionExternalResource,
        ManuscriptRelation, Edition, EditionManuscript, ManuscriptText
    ]
    output_file_name = '../../data/hagiographies_model'
    try:
        generate_data_model_diagram(models, output_file_name)
        os.remove(output_file_name)
    except FileNotFoundError:
        print("Ignored xdg-open error")

if __name__ == "__main__":
    main()