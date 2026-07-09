class JobRecommendation:


    def __init__(self):

        # Sample jobs database

        self.jobs = [

            {
                "title": "Python Developer",
                "skills": [
                    "Python",
                    "SQL",
                    "Git"
                ]
            },


            {
                "title": "Software Engineer",
                "skills": [
                    "Java",
                    "Python",
                    "Database"
                ]
            },


            {
                "title": "Data Analyst",
                "skills": [
                    "Python",
                    "Excel",
                    "SQL"
                ]
            },


            {
                "title": "Web Developer",
                "skills": [
                    "HTML",
                    "CSS",
                    "JavaScript"
                ]
            }

        ]



    # Calculate matching percentage

    def calculate_match(
        self,
        user_skills,
        job_skills
    ):

        matched = 0


        for skill in user_skills:

            if skill in job_skills:

                matched += 1



        percentage = (
            matched / len(job_skills)
        ) * 100


        return round(
            percentage,
            2
        )



    # Generate recommendations

    def get_recommendations(
        self,
        user_skills
    ):


        result = []


        for job in self.jobs:


            score = self.calculate_match(

                user_skills,

                job["skills"]

            )


            result.append(

                {
                    "title": job["title"],
                    "score": score
                }

            )


        # Sort highest match first

        result.sort(

            key=lambda x:x["score"],

            reverse=True

        )


        return result



    # Refresh recommendation

    def refresh(self,user_skills):

        return self.get_recommendations(user_skills)
