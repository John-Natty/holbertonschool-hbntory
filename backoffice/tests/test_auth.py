"""Tests automatisés de l'authentification du Backoffice."""

import re
import unittest
from html import unescape
from urllib.parse import urlsplit

from app import create_app
from app.extensions import db
from app.models import Branch, User
from tests.test_helpers import (
    clean_test_database,
    get_test_database_url,
)


class AuthenticationTestCase(unittest.TestCase):
    """Vérifie la connexion, la session, le CSRF et la déconnexion."""

    def setUp(self):
        """Prépare les données dans PostgreSQL avant chaque test."""
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": (
                    "cle-secrete-reservee-aux-tests-hbntory"
                ),
                "SQLALCHEMY_DATABASE_URI": (
                    get_test_database_url()
                ),
                "SESSION_COOKIE_SECURE": False,
                "WTF_CSRF_ENABLED": True,
            }
        )

        # Crée un client HTTP simulant un navigateur.
        self.client = self.app.test_client()

        with self.app.app_context():
            # Garde les tables et supprime seulement
            # les anciennes données de test.
            clean_test_database()

            branch = Branch(name="Branche de test")
            db.session.add(branch)
            db.session.flush()

            admin = User(
                username="admin",
                role="admin",
                is_active=True,
                branch_id=None,
            )
            admin.set_password("MotDePasseAdmin123!")

            inactive_user = User(
                username="inactive",
                role="common",
                is_active=False,
                branch_id=branch.id,
            )
            inactive_user.set_password(
                "MotDePasseInactif123!"
            )

            db.session.add_all(
                [
                    admin,
                    inactive_user,
                ]
            )
            db.session.commit()

    def tearDown(self):
        """Nettoie les données sans supprimer les tables."""
        with self.app.app_context():
            # Annule une éventuelle transaction incomplète
            # avant de nettoyer la base de test.
            db.session.rollback()
            clean_test_database()
            db.session.remove()

    def get_csrf_token(self, response):
        """Extrait le jeton CSRF contenu dans une page HTML."""
        html_content = response.get_data(as_text=True)

        match = re.search(
            r'name="csrf_token"[^>]*value="([^"]+)"',
            html_content,
        )

        self.assertIsNotNone(
            match,
            "Aucun jeton CSRF n'a été trouvé dans la page.",
        )

        return unescape(match.group(1))

    def login(
        self,
        username="admin",
        password="MotDePasseAdmin123!",
        remember=False,
        query_string=None,
        client=None,
    ):
        """Connecte un utilisateur avec un jeton CSRF valide."""
        current_client = client or self.client

        # Charge le formulaire pour obtenir un jeton CSRF.
        login_page = current_client.get(
            "/auth/login",
            query_string=query_string,
        )
        csrf_token = self.get_csrf_token(login_page)

        form_data = {
            "username": username,
            "password": password,
            "csrf_token": csrf_token,
        }

        if remember:
            form_data["remember"] = "y"

        return current_client.post(
            "/auth/login",
            query_string=query_string,
            data=form_data,
            follow_redirects=False,
        )

    def test_visiteur_anonyme_redirige_vers_connexion(self):
        """Vérifie qu'un visiteur anonyme ne voit pas le dashboard."""
        response = self.client.get(
            "/",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/login", response.location)

    def test_page_de_connexion_accessible(self):
        """Vérifie que le formulaire de connexion est accessible."""
        response = self.client.get("/auth/login")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Connexion",
            response.get_data(as_text=True),
        )

    def test_connexion_valide(self):
        """Vérifie la connexion avec les bons identifiants."""
        response = self.login()

        self.assertEqual(response.status_code, 302)

        with self.client.session_transaction() as session:
            self.assertIn("_user_id", session)

        dashboard = self.client.get("/")

        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(
            "admin",
            dashboard.get_data(as_text=True),
        )

    def test_mot_de_passe_incorrect(self):
        """Vérifie le refus d'un mot de passe incorrect."""
        response = self.login(
            password="MauvaisMotDePasse",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Nom d&#39;utilisateur ou mot de passe incorrect.",
            response.get_data(as_text=True),
        )

        with self.client.session_transaction() as session:
            self.assertNotIn("_user_id", session)

    def test_utilisateur_inactif_refuse(self):
        """Vérifie qu'un utilisateur inactif ne peut pas se connecter."""
        response = self.login(
            username="inactive",
            password="MotDePasseInactif123!",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Nom d&#39;utilisateur ou mot de passe incorrect.",
            response.get_data(as_text=True),
        )

        with self.client.session_transaction() as session:
            self.assertNotIn("_user_id", session)

    def test_connexion_sans_csrf_refusee(self):
        """Vérifie qu'une connexion sans jeton CSRF est refusée."""
        response = self.client.post(
            "/auth/login",
            data={
                "username": "admin",
                "password": "MotDePasseAdmin123!",
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_deconnexion_uniquement_en_post(self):
        """Vérifie que la déconnexion en GET est interdite."""
        self.login()

        response = self.client.get("/auth/logout")

        self.assertEqual(response.status_code, 405)

    def test_deconnexion_sans_csrf_refusee(self):
        """Vérifie que le logout sans jeton CSRF est refusé."""
        self.login()

        response = self.client.post("/auth/logout")

        self.assertEqual(response.status_code, 400)

    def test_deconnexion_valide(self):
        """Vérifie la déconnexion avec un jeton CSRF valide."""
        self.login()

        dashboard = self.client.get("/")
        csrf_token = self.get_csrf_token(dashboard)

        response = self.client.post(
            "/auth/logout",
            data={
                "csrf_token": csrf_token,
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/login", response.location)

        protected_page = self.client.get(
            "/",
            follow_redirects=False,
        )

        self.assertEqual(protected_page.status_code, 302)
        self.assertIn(
            "/auth/login",
            protected_page.location,
        )

    def test_cookie_remember_securise(self):
        """Vérifie les attributs de sécurité du cookie remember."""
        response = self.login(remember=True)

        cookies = response.headers.getlist("Set-Cookie")

        remember_cookie = next(
            (
                cookie
                for cookie in cookies
                if cookie.startswith("remember_token=")
            ),
            None,
        )

        self.assertIsNotNone(remember_cookie)
        self.assertIn("HttpOnly", remember_cookie)
        self.assertIn("SameSite=Lax", remember_cookie)

    def test_redirection_interne_acceptee(self):
        """Vérifie qu'un chemin interne valide est accepté."""
        response = self.login(
            query_string={
                "next": "/",
            }
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            urlsplit(response.location).path,
            "/",
        )

    def test_redirections_dangereuses_refusees(self):
        """Vérifie le blocage des redirections externes."""
        dangerous_targets = [
            "https://evil.example/path",
            "//evil.example/path",
            "///evil.example/path",
            "\\evil.example/path",
            "\\\\evil.example/path",
            "javascript:alert(1)",
            "/%5Cevil.example/path",
            "/%2F%2Fevil.example/path",
        ]

        for target in dangerous_targets:
            with self.subTest(target=target):
                # Utilise une nouvelle session pour chaque destination.
                client = self.app.test_client()

                response = self.login(
                    query_string={
                        "next": target,
                    },
                    client=client,
                )

                self.assertEqual(response.status_code, 302)

                parsed_location = urlsplit(response.location)

                # La redirection doit rester interne.
                self.assertEqual(parsed_location.netloc, "")
                self.assertEqual(parsed_location.path, "/")


if __name__ == "__main__":
    unittest.main()
