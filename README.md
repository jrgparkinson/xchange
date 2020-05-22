# xchange
XC trading exchange

To kill other webservers:
  sudo fuser -k 8000/tcp

To start webserver: 
  python manage.py runserver

Save requirements:
  pip freeze > requirements.tx
Install requirements:
  pip install -r requirements.txt


# Testing
```bash
$ rm -rf db.sqlite3; python manage.py migrate; python xchange/populate.py
```

