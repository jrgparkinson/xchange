# xchange
XC trading exchange

To kill other webservers:
```bash
sudo fuser -k 8000/tcp
```

To start webserver: 
```bash
  python manage.py runserver
```

To start processing tasks:
```bash
python manage.py process_tasks
```

Save requirements:
  pip freeze > requirements.tx
Install requirements:
  pip install -r requirements.txt


# Testing
```bash
$ rm -rf db.sqlite3; python manage.py migrate; python xchange/populate.py
```

