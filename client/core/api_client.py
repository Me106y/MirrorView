import json
import requests

class APIClient:
    def __init__(self, base_url="http://localhost:5001/api"):
        self.base_url = base_url
        self.user_id = None
        self.username = None

    def login(self, username, password):
        try:
            response = requests.post(f"{self.base_url}/auth/login", json={
                "username": username,
                "password": password
            })
            if response.status_code == 200:
                data = response.json()
                self.user_id = data['user_id']
                self.username = data['username']
                return True, data
            
            try:
                error_msg = response.json().get('message', 'Login failed')
            except ValueError:
                error_msg = f"Server Error ({response.status_code}): {response.text[:100]}"
            return False, error_msg
        except Exception as e:
            return False, str(e)

    def register(self, username, password, job_intention, work_experience):
        try:
            response = requests.post(f"{self.base_url}/auth/register", json={
                "username": username,
                "password": password,
                "job_intention": job_intention,
                "work_experience": work_experience
            })
            if response.status_code == 201:
                return True, response.json()
            
            try:
                error_msg = response.json().get('message', 'Registration failed')
            except ValueError:
                error_msg = f"Server Error ({response.status_code}): {response.text[:100]}"
            return False, error_msg
        except Exception as e:
            return False, str(e)

    
    def update_profile(self, target_role, target_jd, work_experience):
        try:
            response = requests.post(f"{self.base_url}/user/{self.user_id}/update_profile", json={
                "target_role": target_role,
                "target_jd": target_jd,
                "work_experience": work_experience
            })
            if response.status_code == 200:
                return True, response.json()
            return False, response.json().get('message', 'Failed to update profile')
        except Exception as e:
            return False, str(e)

    def get_profile(self):
        try:
            response = requests.get(f"{self.base_url}/user/{self.user_id}/profile")
            if response.status_code == 200:
                return True, response.json()
            return False, response.json().get('message', 'Failed to fetch profile')
        except Exception as e:
            return False, str(e)

    def upload_resume(self, file_path):
        try:
            with open(file_path, 'rb') as f:
                files = {'resume': f}
                response = requests.post(
                    f"{self.base_url}/user/{self.user_id}/upload_resume",
                    files=files
                )
            if response.status_code == 200:
                return True, response.json()
            try:
                return False, response.json().get('message', 'Resume upload failed')
            except ValueError:
                return False, f"Server Error ({response.status_code}): {response.text[:100]}"
        except Exception as e:
            return False, str(e)
    def create_interview(self, difficulty="medium", duration=30):
        try:
            response = requests.post(f"{self.base_url}/interview/create", json={
                "user_id": self.user_id,
                # "job_position": job_position, # Removed, fetched from server
                "difficulty": difficulty,
                "duration": duration
            })
            if response.status_code == 201:
                return True, response.json()
            
            try:
                error_msg = response.json().get('message', 'Failed to create interview')
            except ValueError:
                error_msg = f"Server Error ({response.status_code}): {response.text[:100]}"
            return False, error_msg
        except Exception as e:
            return False, str(e)

    def send_message(self, interview_id, content, stream=False, callback=None):
        try:
            url = f"{self.base_url}/interview/{interview_id}/messages"
            payload = {"content": content, "stream": stream}
            
            if stream and callback:
                response = requests.post(url, json=payload, stream=True)
                if response.status_code == 200:
                    for line in response.iter_lines():
                        if line:
                            decoded_line = line.decode('utf-8')
                            if decoded_line.startswith('data: '):
                                json_str = decoded_line[6:]
                                try:
                                    data = json.loads(json_str)
                                    if data.get('done'):
                                        break
                                    if 'content' in data:
                                        callback(data['content'])
                                except json.JSONDecodeError:
                                    pass
                    return True, {"stream_completed": True}
                else:
                    return False, f"Server Error: {response.status_code}"
            
            # Non-streaming fallback
            response = requests.post(url, json=payload)
            if response.status_code == 201:
                return True, response.json()
            
            try:
                error_msg = response.json().get('message', 'Failed to send message')
            except ValueError:
                error_msg = f"Server Error ({response.status_code}): {response.text[:100]}"
            return False, error_msg
        except Exception as e:
            return False, str(e)

    def finish_interview(self, interview_id):
        try:
            response = requests.post(f"{self.base_url}/interview/{interview_id}/finish")
            if response.status_code == 200:
                return True, response.json()
            
            try:
                error_msg = response.json().get('message', 'Failed to finish interview')
            except ValueError:
                error_msg = f"Server Error ({response.status_code}): {response.text[:100]}"
            return False, error_msg
        except Exception as e:
            return False, str(e)

    def create_invite_code(self, interview_id):
        try:
            response = requests.post(f"{self.base_url}/invite/create", json={
                "interview_id": interview_id,
                "user_id": self.user_id
            })
            if response.status_code == 201:
                return True, response.json()
            
            try:
                error_msg = response.json().get('message', 'Failed to create invite code')
            except ValueError:
                error_msg = f"Server Error ({response.status_code}): {response.text[:100]}"
            return False, error_msg
        except Exception as e:
            return False, str(e)

    def join_interview(self, code, listener_id):
        try:
            response = requests.post(f"{self.base_url}/invite/join", json={
                "code": code,
                "listener_id": listener_id
            })
            if response.status_code == 200:
                return True, response.json()
            
            try:
                error_msg = response.json().get('message', 'Failed to join interview')
            except ValueError:
                error_msg = f"Server Error ({response.status_code}): {response.text[:100]}"
            return False, error_msg
        except Exception as e:
            return False, str(e)

    def get_interview_history(self):
        try:
            response = requests.get(f"{self.base_url}/user/{self.user_id}/history")
            if response.status_code == 200:
                return True, response.json()
            return False, response.json().get('message', 'Failed to fetch history')
        except Exception as e:
            return False, str(e)

    def run_resume_match(self, resume_text, jd_text, target_role=""):
        try:
            response = requests.post(
                f"{self.base_url}/careerforge/resume-match",
                json={
                    "resume_text": resume_text,
                    "jd_text": jd_text,
                    "target_role": target_role,
                },
            )
            if response.status_code == 200:
                return True, response.json()
            try:
                return False, response.json().get("message", "Resume match failed")
            except ValueError:
                return False, f"Server Error ({response.status_code}): {response.text[:100]}"
        except Exception as e:
            return False, str(e)

    def run_resume_craft(self, resume_text, target_role="", language="zh", template="", optimization_goal=""):
        try:
            response = requests.post(
                f"{self.base_url}/careerforge/resume-craft",
                json={
                    "resume_text": resume_text,
                    "target_role": target_role,
                    "language": language,
                    "template": template,
                    "optimization_goal": optimization_goal,
                },
            )
            if response.status_code == 200:
                return True, response.json()
            try:
                return False, response.json().get("message", "Resume craft failed")
            except ValueError:
                return False, f"Server Error ({response.status_code}): {response.text[:100]}"
        except Exception as e:
            return False, str(e)

    def run_cover_letter(self, resume_text, jd_text, scenario="email", language="zh", company_name=""):
        try:
            response = requests.post(
                f"{self.base_url}/careerforge/cover-letter",
                json={
                    "resume_text": resume_text,
                    "jd_text": jd_text,
                    "scenario": scenario,
                    "language": language,
                    "company_name": company_name,
                },
            )
            if response.status_code == 200:
                return True, response.json()
            try:
                return False, response.json().get("message", "Cover letter generation failed")
            except ValueError:
                return False, f"Server Error ({response.status_code}): {response.text[:100]}"
        except Exception as e:
            return False, str(e)

    def run_job_hunt(
        self,
        target_role,
        target_jd="",
        work_experience="",
        resume_text="",
        target_regions=None,
        target_cities=None,
        salary_range="",
        hard_requirements=None,
        platforms=None,
    ):
        try:
            response = requests.post(
                f"{self.base_url}/careerforge/job-hunt",
                json={
                    "target_role": target_role,
                    "target_jd": target_jd,
                    "work_experience": work_experience,
                    "resume_text": resume_text,
                    "target_regions": target_regions or [],
                    "target_cities": target_cities or [],
                    "salary_range": salary_range,
                    "hard_requirements": hard_requirements or [],
                    "platforms": platforms or [],
                },
            )
            if response.status_code == 200:
                return True, response.json()
            try:
                return False, response.json().get("message", "Job hunt failed")
            except ValueError:
                return False, f"Server Error ({response.status_code}): {response.text[:100]}"
        except Exception as e:
            return False, str(e)

    def chat_careerforge_agent(self, message, history=None):
        try:
            response = requests.post(
                f"{self.base_url}/careerforge/agent/chat",
                json={
                    "user_id": self.user_id,
                    "message": message,
                    "history": history or [],
                },
            )
            if response.status_code == 200:
                return True, response.json()
            try:
                payload = response.json()
                error_msg = payload.get("error") or payload.get("message") or "Agent chat failed"
                return False, error_msg
            except ValueError:
                return False, f"Server Error ({response.status_code}): {response.text[:120]}"
        except Exception as e:
            return False, str(e)

    def rejoin_interview(self, interview_id):
        try:
            response = requests.get(f"{self.base_url}/interview/{interview_id}/rejoin")
            if response.status_code == 200:
                return True, response.json()
            return False, response.json().get('message', 'Failed to rejoin interview')
        except Exception as e:
            return False, str(e)

    def get_observers(self, interview_id):
        try:
            response = requests.get(f"{self.base_url}/interview/{interview_id}/observers")
            if response.status_code == 200:
                return True, response.json()
            return False, []
        except:
            return False, []

    def get_messages(self, interview_id):
        try:
            response = requests.get(f"{self.base_url}/interview/{interview_id}/messages")
            if response.status_code == 200:
                return True, response.json()
            return False, []
        except:
            return False, []

    def get_interview_status(self, interview_id):
        try:
            response = requests.get(f"{self.base_url}/interview/{interview_id}/status")
            if response.status_code == 200:
                return True, response.json()
            return False, {}
        except:
            return False, {}
