# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import json
import mock
from BeautifulSoup import BeautifulSoup

from django.core import mail
from django.core.urlresolvers import reverse
from django.test import TestCase

from src.accounts.models import User, EmailConfirmation
from src.accounts.tests.factories import UserFactory


class ViewsTests(TestCase):

    def setUp(self):
        self.user = UserFactory(username='user', email='user@test.com', password='user')

    def login(self):
        self.assertTrue(self.client.login(username='user@test.com', password='user'))

    @mock.patch('src.utils.forms.ReCaptchaField.clean', side_effect=lambda data, initial: data)
    def test_create(self, recaptcha_clean_mock):
        url = reverse('accounts:create')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # check invalid data
        data = {
            'username': 'newuser',
            'email': 'newuser@e',
            'password1': 'newuser',
            'password2': 'newuser',
            'captcha': '123'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors['email'])

        # check valid request
        data = {
            'username': 'newuser',
            'email': 'newuser@example.org',
            'password1': 'newuser',
            'password2': 'newuser',
            'captcha': '123'
        }
        mail.outbox = []
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)

        user = User.objects.get(username=data['username'])
        self.assertFalse(user.is_valid_email)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(self.client.login(username=user.email, password=data['password1']))

        # confirm email
        confirmation = user.emailconfirmation_set.all()[:1].get()
        confirmation_url = reverse('accounts:confirm_email', args=[confirmation.confirmation_key])
        response = self.client.get(confirmation_url)
        self.assertEqual(response.status_code, 302)

        user = User.objects.get(pk=user.pk)
        self.assertTrue(user.is_valid_email)

        # try to resend comfirmation email with valid email
        EmailConfirmation.objects.all().delete()
        mail.outbox = []
        resend_url = reverse('accounts:resend_confirmation_email')
        response = self.client.get(resend_url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(EmailConfirmation.objects.exists())
        self.assertFalse(mail.outbox)

        # change email
        user.email = 'newemal@example.org'
        user.save()
        user = User.objects.get(pk=user.pk)
        self.assertEqual(user.emailconfirmation_set.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertFalse(user.is_valid_email)

        # try to resend comfirmation email until old one not expired
        mail.outbox = []
        resend_url = reverse('accounts:resend_confirmation_email')
        response = self.client.get(resend_url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(mail.outbox)
        self.assertEqual(user.emailconfirmation_set.count(), 1)

        # reset confirmation email
        user.emailconfirmation_set.all().delete()
        mail.outbox = []
        response = self.client.get(resend_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(user.emailconfirmation_set.count(), 1)

        # logout
        logout_url = reverse('accounts:logout')
        response = self.client.get(logout_url)
        self.assertEqual(response.status_code, 302)

    def test_profile(self):
        url = reverse('accounts:profile', args=[self.user.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_edit(self):
        self.login()
        url = reverse('accounts:edit')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = {
            'username': 'username',
            'email': 'newemail@example.org'
        }
        mail.outbox = []
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(pk=self.user.pk)
        self.assertEqual(user.email, data['email'])
        self.assertFalse(user.is_valid_email)
        self.assertEqual(len(mail.outbox), 1)

    def test_user_map(self):
        # Create some users with position
        for _ in range(10):
            UserFactory(lng=32.87109375, lat=55.7023550933)

        url = reverse('accounts:map')

        # test anonymous user
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['user_position_json'], 'null')
        other_positions = json.loads(response.context['other_positions_json'])
        self.assertEqual(len(other_positions), 10)

        # test authenticated user
        self.login()
        self.user.lat = 1
        self.user.lng = 1
        self.user.save()

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        user_position = json.loads(response.context['user_position_json'])
        self.assertEqual(user_position, self.user.get_position())
        other_positions = json.loads(response.context['other_positions_json'])
        self.assertEqual(len(other_positions), 10)

    def test_save_user_position(self):
        url = reverse('accounts:save_user_position')

        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)

        self.login()

        response = self.client.post(url, {
            'lng': '3.333',
            'lat': '2.222'
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        position = self.user.get_position()
        self.assertEqual(position['lat'], 2.222)
        self.assertEqual(position['lng'], 3.333)

        response = self.client.post(url, {
            'lng': 'abc',
            'lat': '2.222'
        })
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        position = self.user.get_position()
        self.assertEqual(position['lat'], 2.222)
        self.assertEqual(position['lng'], 3.333)

    def test_profile_posts(self):
        url = reverse('accounts:profile_more_posts', args=(self.user.pk,))

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['object_list']), 0)

    def test_profile_topics(self):
        url = reverse('accounts:profile_more_topics', args=(self.user.pk,))

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['object_list']), 0)

    def test_password_reset(self):
        mail.outbox = []
        reset_password_url = reverse('accounts:password_reset')

        # request email with link to password reset page
        response = self.client.post(reset_password_url, {'email': self.user.email})
        self.assertRedirects(response, reverse('accounts:password_reset_done'))

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        soup = BeautifulSoup(mail.outbox[0].body)
        password_reset_confirm_url = soup.find('a')['href']
        self.assertTrue(password_reset_confirm_url.startswith('http://example.com'))
        password_reset_confirm_url = password_reset_confirm_url[len('http://example.com'):]

        # reset password on password reset page
        response = self.client.get(password_reset_confirm_url)
        self.assertEqual(response.status_code, 200)

        new_password = 'newpassword'
        data = {
            'new_password1': new_password,
            'new_password2': new_password
        }
        response = self.client.post(password_reset_confirm_url, data=data)
        self.assertRedirects(response, reverse('accounts:password_reset_complete'))

        # check new password
        self.assertFalse(self.client.login(username=self.user.email, password='user'))
        self.assertTrue(self.client.login(username=self.user.email, password=new_password))
