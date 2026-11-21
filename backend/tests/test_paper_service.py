import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models.user import User
import services.paper_service as paper_service


class PaperStorageTests(unittest.TestCase):
    def test_pdf_uses_local_storage_without_supabase_configuration(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            test_engine = create_engine(
                f"sqlite:///{root / 'papers.db'}",
                connect_args={"check_same_thread": False},
            )
            Base.metadata.create_all(bind=test_engine)
            test_session_local = sessionmaker(bind=test_engine)

            try:
                with (
                    test_session_local() as db,
                    patch.object(paper_service, "LEGACY_UPLOAD_DIR", root / "uploads"),
                    patch.dict(
                        os.environ,
                        {"SUPABASE_URL": "", "SUPABASE_SERVICE_ROLE_KEY": ""},
                    ),
                ):
                    user = User(email="researcher@example.com", email_verified=True)
                    db.add(user)
                    db.commit()

                    paper = paper_service.create_paper(
                        db=db,
                        pdf_content=b"test pdf",
                        original_filename="paper.pdf",
                        summary="A short summary.",
                        pages=1,
                        user_id=user.id,
                    )

                    self.assertTrue(Path(paper.file_path).is_file())
                    self.assertEqual(paper_service.get_pdf_content(paper), b"test pdf")

                    paper_service.delete_paper(db, paper.id, user.id)
                    self.assertFalse(Path(paper.file_path).exists())
            finally:
                Base.metadata.drop_all(bind=test_engine)
                test_engine.dispose()


if __name__ == "__main__":
    unittest.main()
