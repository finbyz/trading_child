import os

from cryptography.fernet import Fernet
def decrypt_message(encrypted_message):
    """
    Decrypts an encrypted message
    """
    key = os.getenv("ENCRYPT_KEY")
    f = Fernet(key)
    decrypted_message = f.decrypt(eval(encrypted_message))

    return decrypted_message.decode()


def encrypt_message(message):
    """
    Encrypts a message
    """
    key = os.getenv("ENCRYPT_KEY")
    encoded_message = message.encode()
    f = Fernet(key)
    return f.encrypt(encoded_message)
