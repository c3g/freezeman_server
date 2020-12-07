#!/usr/bin/env python
# coding: utf-8

# # Jupyter notebook with django
# 
# 1. pip install django-extensions
# 2. add django-extensions to INSTALLED_APPS in settings.py
# 
# 
# INSTALLED_APPS = (
#     ...
#     'django_extensions',
# )
# 
# 3. pip install jupyter
# 4. python manage.py shell_plus --notebook

# In[1]:


import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fms_core.settings')
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()


# In[2]:


from fms_core.models.container import Container
from fms_core.models.sample import Sample
from fms_core.models.individual import Individual


# In[3]:


individual = Individual.objects.get(id=28)


# In[4]:


print(individual.__dict__)


# In[6]:


# change object directly and save

individual.sex = 'M'
individual.save()
print(individual.__dict__)


# In[8]:


Individual.objects.all().count()


# In[23]:


# count how many individuals of Cohort001

Individual.objects.filter(cohort='Cohort001').count()


# In[24]:


# filter objects and update in bulk

Individual.objects.filter(cohort='Cohort001').update(cohort='New_cohort')


# In[25]:


# count how many individuals of New_cohort

Individual.objects.filter(cohort='New_cohort').count()


# In[27]:


# count how many individuals of Cohort001 after change to New_cohort

Individual.objects.filter(cohort='Cohort001').count()


# In[35]:


Individual.objects.get(id=28).__dict__


# In[36]:


Individual.objects.filter(id=28).update(sex='F')


# In[37]:


Individual.objects.get(id=28).__dict__


# In[38]:


import reversion
from django.contrib.auth.models import User


# In[39]:


# create revision and set comment

with reversion.create_revision():
    individual = Individual.objects.get(id=28)
    individual.sex = 'M'
    # find out how to retrieve a current user in notebook, for now  - user is set to admin
    reversion.set_user(User.objects.get(username='admin'))
    reversion.set_comment('Changed Sex.')
    individual.save()

