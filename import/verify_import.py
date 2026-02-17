from sqlmodel import Session, select, func
from hagiographies_import.db import engine
from hagiographies_import.model import Text, Manuscript, Witness, Edition, EditionManuscriptLink

def verify():
    with Session(engine) as session:
        # Counts
        text_count = session.exec(select(func.count(Text.id))).one()
        ms_count = session.exec(select(func.count(Manuscript.id))).one()
        witness_count = session.exec(select(func.count(Witness.id))).one()
        edition_count = session.exec(select(func.count(Edition.id))).one()
        link_count = session.exec(select(func.count(EditionManuscriptLink.edition_id))).one()
        
        print(f"--- Verification Results ---")
        print(f"Texts: {text_count}")
        print(f"Manuscripts: {ms_count}")
        print(f"Witnesses: {witness_count}")
        print(f"Editions: {edition_count}")
        print(f"Edition-Manuscript Links: {link_count}")
        
        # Samples
        print(f"\n--- Samples ---")
        print("Text (5 samples):")
        for text in session.exec(select(Text).limit(5)):
            print(f"  {text.bhl_number}: {text.title} ({text.origin_place})")
            
        print("\nManuscript (5 samples):")
        for ms in session.exec(select(Manuscript).limit(5)):
            print(f"  {ms.city}, {ms.library} {ms.shelfmark}")
            
        print("\nWitness (5 samples):")
        for w in session.exec(select(Witness).limit(5)):
            print(f"  Text ID {w.text_id} in MS ID {w.manuscript_id}: {w.page_range}")

        print("\nEdition (5 samples):")
        for e in session.exec(select(Edition).limit(5)):
            print(f"  {e.title} ({e.year}): {e.reference}")

        print("\nEdition Links (5 samples via implicit relationship):")
        # To show we can access manuscripts directly from edition
        for e in session.exec(select(Edition).limit(5)):
            if e.manuscripts:
                for ms in e.manuscripts:
                     print(f"  Edition {e.id} -> Manuscript {ms.id} ({ms.library})")
            else:
                print(f"  Edition {e.id} has no linked manuscripts")

if __name__ == "__main__":
    verify()
