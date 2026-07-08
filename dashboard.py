import customtkinter as ctk

from job_recommendation import JobRecommendation
from job_search import JobSearch
from application_tracking import ApplicationTracking


# ==========================
# Theme
# ==========================

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


BG = "#0F172A"
SIDEBAR = "#1E3A8A"
HEADER = "#2563EB"
CARD = "#1E293B"
BUTTON = "#3B82F6"


# ==========================
# Main App
# ==========================

class JobSystem(ctk.CTk):

    def __init__(self):

        super().__init__()

        self.title(
            "Job Matching + Employer Recruitment System"
        )

        self.geometry(
            "1200x700"
        )

        self.configure(
            fg_color=BG
        )


        self.create_sidebar()


        self.content_frame = ctk.CTkFrame(
            self,
            fg_color=BG
        )

        self.content_frame.pack(
            side="right",
            fill="both",
            expand=True
        )


        self.dashboard_page()



    # ==========================
    # Sidebar
    # ==========================

    def create_sidebar(self):

        sidebar = ctk.CTkFrame(
            self,
            width=230,
            fg_color=SIDEBAR,
            corner_radius=0
        )

        sidebar.pack(
            side="left",
            fill="y"
        )


        ctk.CTkLabel(
            sidebar,
            text="JOB MATCH",
            font=("Segoe UI",25,"bold")
        ).pack(
            pady=40
        )


        menu = [

            ("🏠 Dashboard",
             self.dashboard_page),

            ("💼 Job Recommendation",
             self.job_recommendation_page),

            ("🔍 Job Search",
             self.job_search_page),

            ("📄 Application Tracking",
             self.application_tracking_page),

            ("🏢 Employer Recruitment",
             self.placeholder_page),

            ("👤 Profile",
             self.placeholder_page)

        ]


        for text,command in menu:

            ctk.CTkButton(
                sidebar,
                text=text,
                width=190,
                height=40,
                fg_color="transparent",
                hover_color=BUTTON,
                command=command
            ).pack(
                pady=8
            )


        ctk.CTkButton(
            sidebar,
            text="Logout",
            width=190,
            fg_color="#DC2626"
        ).pack(
            side="bottom",
            pady=30
        )



    # ==========================
    # Clear Page
    # ==========================

    def clear_page(self):

        for widget in self.content_frame.winfo_children():

            widget.destroy()



    # ==========================
    # Dashboard
    # ==========================

    def dashboard_page(self):

        self.clear_page()


        main = ctk.CTkFrame(
            self.content_frame,
            fg_color=BG
        )

        main.pack(
            fill="both",
            expand=True
        )


        ctk.CTkLabel(
            main,
            text="Dashboard",
            font=("Segoe UI",30,"bold")
        ).pack(
            pady=30
        )


        ctk.CTkLabel(
            main,
            text="Welcome to Job Matching System",
            font=("Segoe UI",22,"bold")
        ).pack(
            pady=20
        )


        cards = [

            ("Recommended Jobs","25"),

            ("Applications","8"),

            ("Interviews","3"),

            ("Saved Jobs","12")

        ]


        frame = ctk.CTkFrame(
            main,
            fg_color=BG
        )

        frame.pack()


        for title,value in cards:


            card = ctk.CTkFrame(
                frame,
                width=220,
                height=130,
                fg_color=CARD,
                corner_radius=15
            )

            card.pack(
                side="left",
                padx=15
            )


            ctk.CTkLabel(
                card,
                text=value,
                font=("Segoe UI",35,"bold")
            ).pack(
                pady=20
            )


            ctk.CTkLabel(
                card,
                text=title
            ).pack()



    # ==========================
    # Job Recommendation
    # ==========================

    def job_recommendation_page(self):

        self.clear_page()


        main = ctk.CTkFrame(
            self.content_frame,
            fg_color=BG
        )

        main.pack(
            fill="both",
            expand=True
        )


        ctk.CTkLabel(
            main,
            text="Job Recommendation",
            font=("Segoe UI",30,"bold")
        ).pack(
            pady=30
        )


        recommendation = JobRecommendation()


        user_skills = [

            "Python",

            "SQL"

        ]


        jobs = recommendation.get_recommendations(
            user_skills
        )


        for job in jobs:


            card = ctk.CTkFrame(
                main,
                fg_color=CARD
            )

            card.pack(
                fill="x",
                padx=50,
                pady=10
            )


            ctk.CTkLabel(
                card,
                text=job["title"],
                font=("Segoe UI",18,"bold")
            ).pack(
                side="left",
                padx=20,
                pady=15
            )


            ctk.CTkLabel(
                card,
                text=f'{job["score"]}% Match',
                text_color="#22C55E",
                font=("Segoe UI",16,"bold")
            ).pack(
                side="right",
                padx=20
            )



    # ==========================
    # Job Search
    # ==========================

    def job_search_page(self):

        self.clear_page()


        main = ctk.CTkFrame(
            self.content_frame,
            fg_color=BG
        )

        main.pack(
            fill="both",
            expand=True
        )


        ctk.CTkLabel(
            main,
            text="Job Search",
            font=("Segoe UI",30,"bold")
        ).pack(
            pady=20
        )


        search_system = JobSearch()


        keyword = ctk.CTkEntry(
            main,
            placeholder_text="Search job title"
        )

        keyword.pack(
            pady=5
        )


        location = ctk.CTkEntry(
            main,
            placeholder_text="Location"
        )

        location.pack(
            pady=5
        )


        salary = ctk.CTkEntry(
            main,
            placeholder_text="Minimum Salary"
        )

        salary.pack(
            pady=5
        )


        result_box = ctk.CTkTextbox(
            main,
            width=700,
            height=250
        )

        result_box.pack(
            pady=20
        )



        def search():

            result_box.delete(
                "0.0",
                "end"
            )


            jobs = search_system.search_jobs(

                keyword.get(),

                location.get(),

                salary.get()

            )


            for job in jobs:

                result_box.insert(

                    "end",

                    f"""
Job: {job['title']}
Location: {job['location']}
Salary: RM{job['salary']}
Type: {job['type']}
Industry: {job['industry']}

"""

                )



        ctk.CTkButton(
            main,
            text="Search",
            command=search
        ).pack()


        ctk.CTkButton(
            main,
            text="Clear",
            command=lambda:
            result_box.delete("0.0","end")
        ).pack(
            pady=10
        )

    # ==========================
    # Application Tracking
    # ==========================

    def application_tracking_page(self):

        self.clear_page()


        main = ctk.CTkFrame(
            self.content_frame,
            fg_color=BG
        )

        main.pack(
            fill="both",
            expand=True
        )


        ctk.CTkLabel(
            main,
            text="Application Tracking",
            font=("Segoe UI",30,"bold")
        ).pack(
            pady=30
        )



        tracker = ApplicationTracking()


        applications = tracker.get_applications()



        for app in applications:


            card = ctk.CTkFrame(
                main,
                fg_color=CARD
            )


            card.pack(
                fill="x",
                padx=50,
                pady=10
            )


            ctk.CTkLabel(
                card,
                text=f"""
Job: {app['job']}
Company: {app['company']}
Applied Date: {app['date']}
Status: {app['status']}
Details: {app['details']}
""",
                font=("Segoe UI",15),
                justify="left"
            ).pack(
                padx=20,
                pady=15
            )

    # ==========================
    # Future Pages
    # ==========================

    def placeholder_page(self):

        self.clear_page()


        ctk.CTkLabel(
            self.content_frame,
            text="Module Coming Soon",
            font=("Segoe UI",30,"bold")
        ).pack(
            pady=200
        )



# ==========================
# Run
# ==========================

app = JobSystem()

app.mainloop()
