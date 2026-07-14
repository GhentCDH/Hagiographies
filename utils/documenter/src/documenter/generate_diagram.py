from utilities.model import (
    Place, Institution, Author, Typology, ManuscriptType, ImageType,
    ChurchEntity, DatingCentury, VernacularRegion, Text, Codex, Manuscript,
    Image, ExternalResource, EditionExternalResource, ManuscriptRelation,
    Edition, EditionVolume, EditionConsultedVolume, EditionManuscript,
)
from utilities.db import engine
from sqlalchemy_data_model_visualizer import generate_data_model_diagram
import os

def main():
    models = [
        Place, Institution, Author, Typology, ManuscriptType, ImageType,
        ChurchEntity, DatingCentury, VernacularRegion, Text, Codex, Manuscript,
        Image, ExternalResource, EditionExternalResource, ManuscriptRelation,
        Edition, EditionVolume, EditionConsultedVolume, EditionManuscript,
    ]
    output_file_name = '../../data/hagiographies_model'
    try:
        generate_data_model_diagram(models, output_file_name)
        os.remove(output_file_name)
    except FileNotFoundError:
        print("Ignored xdg-open error")

if __name__ == "__main__":
    main()
