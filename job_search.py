class JobSearch:


    def __init__(self):

        # Hardcoded job database

        self.jobs = [

            {
                "title": "Python Developer",
                "location": "Kuala Lumpur",
                "salary": 5000,
                "type": "Full Time",
                "industry": "IT"
            },


            {
                "title": "Software Engineer",
                "location": "Kuala Lumpur",
                "salary": 6000,
                "type": "Full Time",
                "industry": "IT"
            },


            {
                "title": "Data Analyst",
                "location": "Penang",
                "salary": 4500,
                "type": "Full Time",
                "industry": "Data"
            },


            {
                "title": "UI/UX Designer",
                "location": "Johor",
                "salary": 3500,
                "type": "Full Time",
                "industry": "Design"
            },


            {
                "title": "Frontend Developer",
                "location": "Selangor",
                "salary": 4800,
                "type": "Full Time",
                "industry": "IT"
            },


            {
                "title": "Backend Developer",
                "location": "Kuala Lumpur",
                "salary": 5500,
                "type": "Full Time",
                "industry": "IT"
            },


            {
                "title": "Mobile App Developer",
                "location": "Penang",
                "salary": 5200,
                "type": "Full Time",
                "industry": "Software"
            },


            {
                "title": "Cyber Security Analyst",
                "location": "Cyberjaya",
                "salary": 6500,
                "type": "Full Time",
                "industry": "Security"
            },


            {
                "title": "Database Administrator",
                "location": "Kuala Lumpur",
                "salary": 5800,
                "type": "Full Time",
                "industry": "Database"
            },


            {
                "title": "IT Support Technician",
                "location": "Johor",
                "salary": 3000,
                "type": "Part Time",
                "industry": "IT Support"
            },


            {
                "title": "Machine Learning Engineer",
                "location": "Kuala Lumpur",
                "salary": 7500,
                "type": "Full Time",
                "industry": "AI"
            },


            {
                "title": "Business Analyst",
                "location": "Selangor",
                "salary": 5000,
                "type": "Contract",
                "industry": "Business"
            }


        ]



    def search_jobs(
            self,
            keyword="",
            location="",
            salary="",
            job_type="",
            industry=""):


        result = []


        for job in self.jobs:


            # Search by job title

            if keyword.lower() not in job["title"].lower():

                continue



            # Filter location

            if location != "" and location.lower() != job["location"].lower():

                continue



            # Filter minimum salary

            if salary != "" and job["salary"] < int(salary):

                continue



            # Filter employment type

            if job_type != "" and job_type != job["type"]:

                continue



            # Filter industry

            if industry != "" and industry != job["industry"]:

                continue



            result.append(job)



        return result



    def get_all_jobs(self):

        return self.jobs
