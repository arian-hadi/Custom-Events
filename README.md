**🎉 Custom-Events**
*A dynamic, customizable event-management platform*

---

🚀 **Overview:**
Custom-Events is a community-driven event management web application built with Django and Tailwind CSS. It allows administrators to create fully customizable event forms (including text, number, date, and yes/no fields) and empowers users to browse, apply for, and track event applications in one intuitive dashboard.

✨ **Key Features (v1):**

* 📝 Admins can post events with up to 4 custom question fields
* 🔎 Users can search events, fill out dynamic forms, and submit applications
* 🧑‍⚖️ Admin dashboard for reviewing and changing application status (approve/deny)
* 🎨 Responsive UI styled with Django-Tailwind
* 🎠 Interactive intro carousel built with Swiper.js

🛍️ **Planned Features (v2):**

* 🛒 Embedded “shop” section surfacing products from Amazon/Ebay (no checkout)

---

🧰 **Tech Stack:**

* ⚙️ Backend: Django
* 🎨 Styling: Tailwind CSS (via django-tailwind)
* 🛢️ Database: PostgreSQL
* 🖼️ Carousel/Intro: Swiper.js
* ☁️ Hosting: Railway

---

⚙️ **Installation & Setup:**

1. Clone the repo
   `git clone https://github.com/arian-hadi/Custom-Events.git`
   `cd Custom-Events`

2. Create and activate a virtual environment
   `python3 -m venv .venv`
   `source .venv/bin/activate`
   
3. Install dependencies
   `pip install -r requirements.txt`

4. Copy the example environment file
   `cp .env.example .env`
   Then open `.env` and fill in your actual values:

   ```
   SECRET_KEY=your_django_secret_key  
   DEBUG=True  
   DATABASE_URL=postgres://user:password@localhost:5432/db_name  
   ```

5. Apply migrations
   `python manage.py migrate`

6. Build Tailwind assets
   `python manage.py tailwind install`
   `python manage.py tailwind start`

7. Start development server
   `python manage.py runserver`
   The site will be live at `http://127.0.0.1:8000/`

---

🌍 **Deployment (Railway):**
Railway makes Django deployment easy.
Steps:

* Push your code to GitHub
* Go to [https://railway.app](https://railway.app) and create a new project
* Connect your GitHub repo
* Add these environment variables in Railway’s settings:

  * `SECRET_KEY`
  * `DEBUG=False`
  * `DATABASE_URL` (Railway auto-generates this for Postgres)
* Set your custom domain (`yourdomain.com`) in Railway settings
* Add the domain to your `ALLOWED_HOSTS` in `settings.py` (you’ve already done this ✅)

---

🧑‍💻 **Usage:**

* Visit `http://127.0.0.1:8000/` in development
* Admins can create events and define custom fields
* Users can browse and apply to events
* Track applications under the dashboard
* Application statuses: Pending ⏳, Accepted ✅, Rejected ❌

---

🛠️ **Configuration Notes:**

* Tailwind config: `theme/`
* Swiper setup: `static/js/slider.js`
* Custom field types: `events/models.py`
* Allowed hosts (already configured):

  * localhost
  * 127.0.0.1

---

🗺️ **Roadmap:**

* [ ] v2: Product showcase linking to Amazon/Ebay
* [ ] User profiles and social auth
* [ ] Email alerts for application status updates

---

🤝 **Contributing:**

1. Fork the repository
2. Create a new branch
3. Make your changes
4. Push your changes
5. Open a Pull Request 🚀

Please follow Django best practices and PEP8 🐍

---

📬 **Contact:**
Created and maintained by **arian-hadi**
GitHub: [https://github.com/arian-hadi](https://github.com/arian-hadi)
For suggestions or issues, open a GitHub issue!

**Screenshots:**
* About page
  ![Screenshot 2025-05-06 153213](https://github.com/user-attachments/assets/ede40440-7c3e-4497-80e8-507941a836e5)
![Screenshot 2025-05-06 153237](https://github.com/user-attachments/assets/ec7fb4dd-4ee7-41ef-883a-0ca168529151)

* Event Page
  ![Screenshot 2025-05-06 153300](https://github.com/user-attachments/assets/c399e898-1a02-4ff9-af24-a8fb526ad757)
![Screenshot 2025-05-07 222229](https://github.com/user-attachments/assets/77c5ca23-4491-4975-b289-dd9b693175ea)

* User & Admin Dashboard
![Screenshot 2025-05-06 153327](https://github.com/user-attachments/assets/51a1d27b-88ed-4e10-b9aa-5849305cdfec)
![Screenshot 2025-05-06 153845](https://github.com/user-attachments/assets/29a47e3a-4f2f-4fdb-b858-a0ff154ad6a5)

* Custom Fields For Events Creation
![Screenshot 2025-05-06 153412](https://github.com/user-attachments/assets/41b0ff10-16e8-4ee2-95f8-410c3e1fa04a)
![Screenshot 2025-05-06 153445](https://github.com/user-attachments/assets/74d0cbee-af68-45c4-9f0d-b3b0c331e381)

* Event forms fields for Users

  ![Screenshot 2025-05-06 153814](https://github.com/user-attachments/assets/e321b218-1000-446b-a830-5d5e03865336)

