import streamlit as st
import os
import json
import tempfile
from pathlib import Path
import asyncio
from datetime import datetime

# Import your existing modules
from llama_resume_parser import ResumeParser
from standardizer import ResumeStandardizer
from db_manager import ResumeDBManager
from OCR_resume_parser import ResumeParserwithOCR
from final_retriever import run_retriever, render_formatted_resume  # Retriever engine
from job_matcher import JobMatcher, JobDescriptionAnalyzer  # Import both classes from job_matcher

# Set page configuration
st.set_page_config(
    page_title="HR Resume Bot",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for improved UI
st.markdown("""
<style>
.main {
    padding: 2rem;
}
.stButton button {
    width: 100%;
}
.card {
    background-color: #f9f9f9;
    border-radius: 10px;
    padding: 20px;
    margin-bottom: 15px;
    border-left: 5px solid #0068c9;
}
.card:hover {
    box-shadow: 0 4px 8px rgba(0,0,0,0.1);
}
.candidate-name {
    font-size: 20px;
    font-weight: bold;
    color: #0068c9;
}
.contact-info {
    color: #444;
    margin: 10px 0;
}
.score-info {
    color: #666;
    font-size: 14px;
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px solid #eee;
}
.accepted {
    color: #28a745;
    font-weight: bold;
}
.rejected {
    color: #dc3545;
    font-weight: bold;
}
.result-count {
    font-size: 18px;
    font-weight: bold;
    margin-bottom: 20px;
}
</style>
""", unsafe_allow_html=True)

# Sidebar for app navigation and explanations
st.sidebar.title("HR Assistance Bot")
page = st.sidebar.selectbox("Navigate", [
    "Resume Search Engine",
    "Job Description Matcher",  # New page
    "Upload & Process", 
    "Database Management", 
], index=0)  # Set index=0 to make Resume Search Engine the default

# Add explanatory text based on selected page
if page == "Resume Search Engine":
    st.sidebar.markdown("""
    """)
elif page == "Job Description Matcher":
    st.sidebar.markdown("""
    ### 🎯 Job Description Matcher
    This page allows you to:
    1. Input a job description
    2. Automatically extract relevant keywords
    3. Score and rank candidates based on their match
    4. View detailed matching analysis
    5. See only the most relevant candidates
    """)
elif page == "Upload & Process":
    st.sidebar.markdown("""
    ### 📤 Upload & Process
    This page allows you to:
    1. Upload multiple resume files (PDF/DOCX)
    2. Automatically process them through our pipeline:
       - Parse and extract content
       - Standardize the format
       - Store in database
    3. Preview processed resumes
    """)
elif page == "Database Management":
    st.sidebar.markdown("""
    ### 💾 Database Management
    This page enables you to:
    1. View all stored resumes
    2. Search resumes by specific fields
    3. View detailed resume information
    4. Manage the resume database
    """)

# Initialize session state for tracking job progress
if "processing_complete" not in st.session_state:
    st.session_state.processing_complete = False
if "standardizing_complete" not in st.session_state:
    st.session_state.standardizing_complete = False
if "db_upload_complete" not in st.session_state:
    st.session_state.db_upload_complete = False
if "processed_files" not in st.session_state:
    st.session_state.processed_files = []
if "standardized_files" not in st.session_state:
    st.session_state.standardized_files = []
if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = []


def process_uploaded_files(uploaded_files):
    """Process uploaded resume files through the parser"""
    st.session_state.processing_complete = False
    st.session_state.standardizing_complete = False
    st.session_state.db_upload_complete = False
    st.session_state.processed_files = []

    st.write(f"Processing {len(uploaded_files)} files...")
    progress_bar = st.progress(0)
    status_text = st.empty()

    total_files = len(uploaded_files)
    processed_count = 0

    files_to_process = list(uploaded_files)

    for i, uploaded_file in enumerate(files_to_process):
        file_name = uploaded_file.name
        status_text.text(f"Processing {i+1}/{total_files}: {file_name}")

        temp_file_path = os.path.join(temp_dir, file_name)
        with open(temp_file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        file_ext = Path(file_name).suffix.lower()
        parser = ResumeParser()  # Instantiate inside loop to avoid event loop issues

        if file_ext not in parser.SUPPORTED_EXTENSIONS:
            st.warning(f"Skipping {file_name}: Unsupported file type {file_ext}")
            continue

        try:
            parsed_resume = parser.parse_resume(temp_file_path)
            if parsed_resume:
                parsed_resume["timestamp"] = datetime.now().isoformat()
                parsed_resume["original_filename"] = file_name

                output_path = parsed_dir / f"{Path(file_name).stem}.json"
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(parsed_resume, f, indent=2, ensure_ascii=False)

                st.session_state.processed_files.append(output_path)
                processed_count += 1
            else:
                st.warning(f"No content extracted from {file_name}")
        except Exception as e:
            st.error(f"Error parsing {file_name}: {str(e)}")

        progress_bar.progress((i + 1) / total_files)

    status_text.text(f"✅ Processed {processed_count}/{total_files} files")
    st.session_state.processing_complete = True
    
async def standardize_resumes():
    """Standardize the parsed resumes using ResumeStandardizer"""
    st.session_state.standardizing_complete = False
    st.session_state.standardized_files = []
    
    # Show status
    st.write(f"Standardizing {len(st.session_state.processed_files)} files...")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Initialize the standardizer
    try:
        standardizer = ResumeStandardizer()
    except ValueError as e:
        st.error(f"Error initializing standardizer: {e}")
        return
    
    total_files = len(st.session_state.processed_files)
    standardized_count = 0
    
    # Create a copy of processed files list to prevent any potential issues with iteration
    files_to_standardize = list(st.session_state.processed_files)
    
    for i, file_path in enumerate(files_to_standardize):
        status_text.text(f"Standardizing {i+1}/{total_files}: {file_path.name}")
        
        # Modify the standardizer to use our temp paths
        output_path = standardized_dir / file_path.name
        
        if output_path.exists():
            st.session_state.standardized_files.append(output_path)
            standardized_count += 1
            progress_bar.progress((i + 1) / total_files)
            continue
        
        try:
            with open(file_path, encoding="utf-8") as f:
                raw = json.load(f)
            
            content = raw.get("content", "")
            links = raw.get("links", [])
            
            if not content.strip():
                st.warning(f"Empty content in {file_path.name}, skipping.")
                continue
            
            prompt = standardizer.make_standardizer_prompt(content, links)
            raw_response = await standardizer.call_azure_llm(prompt)
            
            # Log raw response
            raw_log_path = standardized_dir / f"{file_path.stem}_raw.md"
            with open(raw_log_path, "w", encoding="utf-8") as f:
                f.write(raw_response)
            
            cleaned_json = standardizer.clean_llm_response(raw_response)
            parsed_json = json.loads(cleaned_json)
            
            # Add timestamp, file source and original filename
            parsed_json["timestamp"] = datetime.now().isoformat()
            parsed_json["source_file"] = str(file_path)
            if "original_filename" in raw:
                parsed_json["original_filename"] = raw["original_filename"]
            
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(parsed_json, f, indent=2, ensure_ascii=False)
            
            st.session_state.standardized_files.append(output_path)
            standardized_count += 1
        except Exception as e:
            st.error(f"Error standardizing {file_path.name}: {str(e)}")
        
        # Update progress
        progress_bar.progress((i + 1) / total_files)
    
    status_text.text(f"✅ Standardized {standardized_count}/{total_files} files")
    st.session_state.standardizing_complete = True

def convert_objectid_to_str(obj):
    """Recursively turn any ObjectId into its string form."""
    if isinstance(obj, dict):
        return {k: convert_objectid_to_str(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_objectid_to_str(i) for i in obj]
    # Match ObjectId by name to avoid importing bson here
    elif type(obj).__name__ == "ObjectId":
        return str(obj)
    else:
        return obj
    
def upload_to_mongodb():
    """Upload standardized resumes to MongoDB"""
    st.session_state.db_upload_complete = False
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Initialize DB manager
    try:
        db_manager = ResumeDBManager()
    except Exception as e:
        st.error(f"Error connecting to MongoDB: {e}")
        return
    
    total_files = len(st.session_state.standardized_files)
    uploaded_count = 0
    
    for i, file_path in enumerate(st.session_state.standardized_files):
        status_text.text(f"Uploading {i+1}/{total_files}: {file_path.name}")
        
        try:
            with open(file_path, encoding="utf-8") as f:
                resume_data = json.load(f)
            
            # Insert or update in MongoDB
            db_manager.insert_or_update_resume(resume_data)
            uploaded_count += 1
            st.session_state.uploaded_files.append(file_path.name)
        except Exception as e:
            st.error(f"Error uploading {file_path.name}: {e}")
        
        # Update progress
        progress_bar.progress((i + 1) / total_files)
    
    status_text.text(f"✅ Uploaded {uploaded_count}/{total_files} resumes to MongoDB")
    st.session_state.db_upload_complete = True

def validate_and_reprocess_resumes(uploaded_files):
    """Validate standardized resumes and reprocess if 'name' is missing."""
    st.write("🔍 Validating standardized resumes...")
    reprocessed_count = 0

    for file_path in st.session_state.standardized_files:
        try:
            with open(file_path, encoding="utf-8") as f:
                resume_data = json.load(f)

            # Check if 'name' is missing
            if not resume_data.get("name") or len(resume_data.get("name").split()[0]) < 2:
                st.warning(f"⚠️ Missing 'name' in {file_path.name}. Reprocessing...")
                reprocessed_count += 1

                # Find the original file in uploaded files
                original_file_name = file_path.stem  # Remove .json extension
                original_file = next(
                    (file for file in uploaded_files if Path(file.name).stem == original_file_name),
                    None
                )

                if not original_file:
                    st.error(f"❌ Original file for {file_path.name} not found in uploaded files.")
                    continue

                # Save the uploaded file temporarily
                temp_file_path = temp_dir / original_file.name
                with open(temp_file_path, "wb") as f:
                    f.write(original_file.getbuffer())

                # Re-parse the original file
                parser = ResumeParserwithOCR()
                parsed_resume = parser.parse_resume(temp_file_path)

                if parsed_resume:
                    # Save parsed data
                    parsed_output_path = parsed_dir / f"{original_file_name}.json"
                    parser.save_to_json(parsed_resume, parsed_output_path)

                    # Re-standardize the parsed data
                    standardizer = ResumeStandardizer()
                    content = parsed_resume.get("content", "")
                    links = parsed_resume.get("links", [])
                    prompt = standardizer.make_standardizer_prompt(content, links)
                    raw_response = asyncio.run(standardizer.call_azure_llm(prompt))
                    cleaned_json = standardizer.clean_llm_response(raw_response)
                    parsed_json = json.loads(cleaned_json)

                    # Add metadata
                    parsed_json["timestamp"] = datetime.now().isoformat()
                    parsed_json["source_file"] = str(temp_file_path)
                    parsed_json["original_filename"] = original_file.name

                    # Save re-standardized data
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(parsed_json, f, indent=2, ensure_ascii=False)

                    st.success(f"✅ Reprocessed and standardized: {file_path.name}")
                else:
                    st.error(f"❌ Failed to re-parse {original_file.name}")
        except Exception as e:
            st.error(f"Error validating {file_path.name}: {e}")

    st.write(f"🔄 Reprocessed {reprocessed_count} resumes with missing 'name'.")

# Create temp directories for processing
temp_dir = Path(tempfile.gettempdir()) / "resume_processor"
parsed_dir = temp_dir / "parsed"
standardized_dir = temp_dir / "standardized"
for directory in [parsed_dir, standardized_dir]:
    directory.mkdir(parents=True, exist_ok=True)

# -------------------
# Page: Boolean Search Engine
# -------------------
if page == "Resume Search Engine":
    # Prevent duplicate set_page_config calls in the retriever module
    original_spc = st.set_page_config
    st.set_page_config = lambda *args, **kwargs: None

    try:
        run_retriever()
    finally:
        st.set_page_config = original_spc

# -------------------
# Page: Job Description Matcher
# -------------------
elif page == "Job Description Matcher":
    st.title("🎯 Job Description Matcher")
    st.markdown("""
    Input a job description and let our AI-powered system:
    1. Extract relevant keywords  
    2. Score candidates based on match  
    3. Show detailed analysis  
    4. Retailor their resumes on the fly  
    """)

    # --- NEW: Search & Retailor for a Specific Candidate ---
    st.header("🔎 Search & Retailor for a Specific Candidate")
    search_field = st.selectbox("Search by", ["name", "email"])
    search_value = st.text_input(f"Enter candidate {search_field}")
    job_description_single = st.text_area("Enter Job Description for This Candidate", height=150, key="single_jd")

    if st.button("Find & Retailor for This Candidate"):
        if not search_value or not job_description_single.strip():
            st.warning("Please enter both candidate info and job description.")
        else:
            from db_manager import ResumeDBManager
            db_manager = ResumeDBManager()
            query = {search_field: {"$regex": f"^{search_value}$", "$options": "i"}}
            results = db_manager.find(query)
            if not results:
                st.error("No candidate found with that info.")
            else:
                # If multiple, let user pick
                if len(results) > 1:
                    st.warning("Multiple candidates found. Please select the correct one.")
                    options = [
                        f"{c.get('name', 'Unknown')} | {c.get('email', 'No email')} | {c.get('phone', 'No phone')}"
                        for c in results
                    ]
                    selected = st.selectbox("Select Candidate", options)
                    idx = options.index(selected)
                    candidate = results[idx]
                else:
                    candidate = results[0]
                st.success(f"Found candidate: {candidate.get('name', 'Unknown')}")
                analyzer = JobDescriptionAnalyzer()
                keywords = analyzer.extract_keywords(job_description_single)
                matcher = JobMatcher()
                retailored = matcher.resume_retailor.retailor_resume(
                    convert_objectid_to_str(candidate),
                    keywords["keywords"]
                )
                # Beautified card replaced with formatted view
                tab1, tab2 = st.tabs(["Formatted View", "JSON View"])
                with tab1:
                    # Use the same formatted resume renderer as elsewhere
                    render_formatted_resume(retailored)
                with tab2:
                    st.json(retailored)
                # Download
                payload = json.dumps(retailored, indent=2)
                st.download_button(
                    "📥 Download Retailored Resume",
                    data=payload,
                    file_name=f"{candidate.get('name','candidate').replace(' ', '_')}_retailored.json",
                    mime="application/json"
                )

    # Init session state
    if "matcher" not in st.session_state:
        st.session_state.matcher = None
    if "extracted_keywords" not in st.session_state:
        st.session_state.extracted_keywords = set()
    if "job_matcher_results" not in st.session_state:
        st.session_state.job_matcher_results = []

    job_description = st.text_area(
        "📝 Enter Job Description",
        height=200,
        placeholder="Paste the job description here."
    )

    if job_description and st.button("🔍 Find Matching Candidates", type="primary"):
        progress = st.progress(0)
        status = st.empty()
        with st.spinner("Analyzing and matching candidates…"):
            # create & store matcher
            matcher = JobMatcher()
            st.session_state.matcher = matcher

            # extract & store keywords
            analyzer = JobDescriptionAnalyzer()
            kw = analyzer.extract_keywords(job_description)
            st.session_state.extracted_keywords = kw["keywords"]

            # find & score
            results = matcher.find_matching_candidates(
                job_description,
                progress_bar=progress,
                status_text=status
            )
            st.session_state.job_matcher_results = results

        progress.empty()
        status.empty()

    # Show keywords
    if st.session_state.extracted_keywords:
        st.subheader("🔑 Extracted Keywords")
        st.write(", ".join(sorted(st.session_state.extracted_keywords)))

    # Display matched candidates
    if st.session_state.job_matcher_results:
        accepted = [c for c in st.session_state.job_matcher_results if c["status"] == "Accepted"]
        if accepted:
            st.success(f"✅ Found {len(accepted)} matching candidates")
            st.subheader("📋 Detailed Candidate Profiles")

            for cand in accepted:
                st.markdown(f"""
                <div class="card">
                  <div class="candidate-name">{cand['name']}</div>
                  <div class="contact-info">
                    📧 {cand['email']} | 📱 {cand['phone']}
                  </div>
                  <div class="score-info">
                    Score: {cand['score']}/100 | 
                    Status: <span class="{cand['status'].lower()}">{cand['status']}</span>
                  </div>
                </div>
                """, unsafe_allow_html=True)

                with st.expander("📊 View Matching Analysis"):
                    st.markdown(cand["reason"])
                    col1, col2 = st.columns(2)

                with col1:
                    if st.button("📄 View Full Resume", key=f"view_{cand['mongo_id']}"):
                        clean_resume = convert_objectid_to_str(cand["resume"])
                        st.subheader("🗂️ Original Resume")
                        st.json(clean_resume)

                with col2:
                    if st.button("✍️ Retailor Resume", key=f"retailor_{cand['mongo_id']}"):
                        matcher = st.session_state.get("matcher")
                        if matcher is None:
                            st.error("Please re-run 'Find Matching Candidates' first.")
                        else:
                            st.write("**Using Keywords:**", list(st.session_state.extracted_keywords))
                            with st.spinner("Retailoring resume…"):
                                safe_resume = convert_objectid_to_str(cand["resume"])
                                new_res = matcher.resume_retailor.retailor_resume(
                                    safe_resume,
                                    st.session_state.extracted_keywords
                                )
                            if new_res:
                                clean_new = convert_objectid_to_str(new_res)
                                st.subheader("✏️ Retailored Resume")
                                st.json(clean_new)
                                payload = json.dumps(clean_new, indent=2)
                                st.download_button(
                                    "📥 Download Retailored Resume",
                                    data=payload,
                                    file_name=f"{cand['name'].replace(' ', '_')}_retailored.json",
                                    mime="application/json",
                                    key=f"dl_{cand['mongo_id']}"
                                )
                            else:
                                st.error("❌ Retailoring failed.")
# ─────────────────────────────────────────────

        else:
            st.info("🔍 No matching candidates found.")
    elif job_description:
        st.info("👆 Click 'Find Matching Candidates' to start.")
    else:
        st.info("👆 Enter a job description to begin matching.")



# -------------------
# Page: Upload & Process Resumes
# -------------------
elif page == "Upload & Process":
    st.title("📄 Resume Processing Pipeline")
    st.markdown("""
    ### Streamlined Resume Processing
    Upload your resume files and let our AI-powered pipeline handle the rest. The system will automatically:
    1. Extract and parse content from your resumes
    2. Standardize the information into a consistent format
    3. Store the processed data in our database
    
    Supported formats: PDF, DOCX
""")

    uploaded_files = st.file_uploader(
        "📤 Upload Resume Files", 
        type=["pdf", "docx"], 
        accept_multiple_files=True,
        key="resume_uploader",
        help="Upload PDF or DOCX resume files"
    )

    # Track uploaded files in session state for persistence
    if "uploaded_file_names" not in st.session_state:
        st.session_state.uploaded_file_names = []

    # Update the list of uploaded file names
    if uploaded_files:
        current_file_names = [file.name for file in uploaded_files]
        if sorted(current_file_names) != sorted(st.session_state.uploaded_file_names):
            st.session_state.uploaded_file_names = current_file_names
            st.session_state.processing_complete = False
            st.session_state.standardizing_complete = False
            st.session_state.db_upload_complete = False
            st.session_state.processed_files = []
            st.session_state.standardized_files = []
            st.session_state.uploaded_files = []

    # Combined processing button
    if uploaded_files:
        if st.button("🚀 Process Resumes", type="primary", use_container_width=True):
            with st.spinner("Processing resumes..."):
                # Step 1: Parse
                process_uploaded_files(uploaded_files)
                st.success("✅ Parsing complete!")
                
                # Step 2: Standardize
                asyncio.run(standardize_resumes())
                st.success("✅ Standardization complete!")

                # Step 3: Validate and reprocess if necessary
                validate_and_reprocess_resumes(uploaded_files)
                
                # Step 4: Upload to MongoDB
                upload_to_mongodb()
                st.success("✅ Database upload complete!")
    else:
        st.info("👆 Please upload resume files to begin processing")

    # Display processing status
    st.subheader("📊 Processing Status")
    status_col1, status_col2, status_col3 = st.columns(3)
    with status_col1:
        if st.session_state.processing_complete:
            st.success(f"✅ Parsed {len(st.session_state.processed_files)} files")
        else:
            st.info("⏳ Waiting for parsing...")
    with status_col2:
        if st.session_state.standardizing_complete:
            st.success(f"✅ Standardized {len(st.session_state.standardized_files)} files")
        elif st.session_state.processing_complete:
            st.info("⏳ Ready to standardize")
        else:
            st.info("⏳ Waiting for parsing...")
    with status_col3:
        if st.session_state.db_upload_complete:
            st.success(f"✅ Uploaded {len(st.session_state.uploaded_files)} files to MongoDB")
        elif st.session_state.standardizing_complete:
            st.info("⏳ Ready to upload to MongoDB")
        else:
            st.info("⏳ Waiting for standardization...")

    # Display file previews if processed
    if st.session_state.standardized_files:
        st.subheader("👀 Preview Processed Resumes")
        selected_file = st.selectbox(
            "Select a resume to preview", 
            options=[f.name for f in st.session_state.standardized_files]
        )
        if selected_file:
            file_path = standardized_dir / selected_file
            with open(file_path, "r", encoding="utf-8") as f:
                resume_data = json.load(f)
            
            # Create a more visually appealing preview
            st.markdown("---")
            col1, col2 = st.columns([1, 2])
            with col1:
                st.markdown(f"### 👤 {resume_data.get('name', 'Unknown Name')}")
                st.markdown(f"📧 **Email:** {resume_data.get('email', 'No email')}")
                st.markdown(f"📱 **Phone:** {resume_data.get('phone', 'No phone')}")
                st.markdown(f"📍 **Location:** {resume_data.get('location', 'No location')}")
                if resume_data.get('skills'):
                    st.markdown("### 🛠️ Skills")
                    st.write(", ".join(resume_data.get('skills', [])))
            with col2:
                if resume_data.get('experience'):
                    st.markdown("### 💼 Experience")
                    for exp in resume_data.get('experience', [])[:2]:
                        st.markdown(f"""
                        **{exp.get('title')}** at {exp.get('company')}
                        *{exp.get('duration', 'N/A')}*
                        """)
            if st.checkbox("Show Raw JSON"):
                st.json(resume_data)

# -------------------
# Page: Database Management
# -------------------
elif page == "Database Management":
    st.title("💾 Resume Database Management")
    st.markdown("""
    ### Database Operations
    Manage and query your resume database with powerful search capabilities.
""")

    try:
        db_manager = ResumeDBManager()
        st.subheader("🔍 Query Resumes")
        query_type = st.radio("Select Query Type", ["View All Resumes", "Search by Field"])
        
        if query_type == "View All Resumes":
            if "all_resumes_results" not in st.session_state:
                st.session_state.all_resumes_results = []
            if st.button("📥 Fetch All Resumes", use_container_width=True) or st.session_state.all_resumes_results:
                with st.spinner("Fetching resumes..."):
                    if not st.session_state.all_resumes_results:
                        st.session_state.all_resumes_results = db_manager.find({})
                    results = st.session_state.all_resumes_results
                    st.success(f"Found {len(results)} resumes")
                    if results:
                        resume_data = []
                        for res in results:
                            resume_data.append({
                                "ID": res.get("_id", "N/A"),
                                "Name": res.get("name", "N/A"),
                                "Email": res.get("email", "N/A"),
                                "Skills": ", ".join(res.get("skills", [])[:3]) + ("..." if len(res.get("skills", [])) > 3 else "")
                            })
                        st.dataframe(resume_data, use_container_width=True)
                        
                        resume_options = []
                        st.session_state.resume_display_map = {}
                        for res in results:
                            display_text = f"{res.get('name', 'Unknown')} - {res.get('email', 'No email')}"
                            resume_options.append(display_text)
                            st.session_state.resume_display_map[display_text] = res
                        
                        selected_resume_option = st.selectbox(
                            "Select resume to view details", 
                            options=resume_options if resume_options else ["No resumes found"],
                            key="resume_selector"
                        )
                        
                        if selected_resume_option and "No resumes found" not in selected_resume_option:
                            selected_resume = st.session_state.resume_display_map.get(selected_resume_option)
                            if selected_resume:
                                st.json(selected_resume)

                                # Add delete button with confirmation logic
                                if "delete_confirmation" not in st.session_state:
                                    st.session_state.delete_confirmation = False

                                if not st.session_state.delete_confirmation:
                                    if st.button("🗑️ Delete Resume", key="delete_button"):
                                        st.session_state.delete_confirmation = True
                                else:
                                    # Simulate a pop-up-like experience
                                    with st.container():
                                        st.error("⚠️ Are you sure you want to delete this resume? This action cannot be undone.")
                                        col1, col2 = st.columns(2)
                                        with col1:
                                            if st.button("Yes, Delete", key="confirm_delete_button"):
                                                try:
                                                    db_manager.delete_resume({"_id": selected_resume["_id"]})
                                                    st.success(f"✅ Deleted resume: {selected_resume.get('name', 'Unknown')}")
                                                    # Refresh the results after deletion
                                                    st.session_state.all_resumes_results = db_manager.find({})
                                                    st.session_state.delete_confirmation = False  # Reset confirmation state
                                                except Exception as e:
                                                    st.error(f"Error deleting resume: {e}")
                                        with col2:
                                            if st.button("Cancel", key="cancel_delete_button"):
                                                st.info("Deletion canceled.")
                                                st.session_state.delete_confirmation = False  # Reset confirmation state
                            else:
                                st.error("Could not find the selected resume. Please try again.")
        
        elif query_type == "Search by Field":
            col1, col2 = st.columns(2)
            with col1:
                search_field = st.selectbox(
                "Search Field", 
                ["name", "email", "skills", "experience.company", "education.institution"]
            )
            with col2:
                search_value = st.text_input("Search Value")
            
            if st.button("🔍 Search", use_container_width=True):
                if search_value:
                    query = {}
                    if search_field == "skills":
                        query = {search_field: {"$in": [search_value]}}
                    elif "." in search_field:
                        query = {search_field: {"$regex": search_value, "$options": "i"}}
                    else:
                        query = {search_field: {"$regex": search_value, "$options": "i"}}
                    
                    with st.spinner("Searching..."):
                        results = db_manager.find(query)
                        if results:
                            st.success(f"Found {len(results)} matching resumes")
                            search_options = []
                            search_map = {}
                            for res in results:
                                display_text = f"{res.get('name', 'Unknown')} - {res.get('email', 'No email')}"
                                search_options.append(display_text)
                                search_map[display_text] = res
                            
                            # Store search results and map in session state
                            st.session_state.search_options = search_options
                            st.session_state.search_map = search_map
                        else:
                            st.warning("No matching resumes found")
                else:
                    st.warning("Please enter a search value")
            
            # Display search results if available
            if "search_options" in st.session_state and st.session_state.search_options:
                selected_search_result = st.selectbox(
                    "Select resume to view details", 
                    options=st.session_state.search_options,
                    key="search_selector"
                )
                
                if selected_search_result:
                    selected_resume = st.session_state.search_map.get(selected_search_result)
                    if selected_resume:
                        st.json(selected_resume)

                        # Add delete button with confirmation logic
                        if "delete_confirmation" not in st.session_state:
                            st.session_state.delete_confirmation = False

                        if not st.session_state.delete_confirmation:
                            if st.button("🗑️ Delete Resume", key="delete_button"):
                                st.session_state.delete_confirmation = True
                        else:
                            # Simulate a pop-up-like experience
                            with st.container():
                                st.error("⚠️ Are you sure you want to delete this resume? This action cannot be undone.")
                                col1, col2 = st.columns(2)
                                with col1:
                                    if st.button("Yes, Delete", key="confirm_delete_button"):
                                        try:
                                            db_manager.delete_resume({"_id": selected_resume["_id"]})
                                            st.success(f"✅ Deleted resume: {selected_resume.get('name', 'Unknown')}")
                                            # Refresh the results after deletion
                                            st.session_state.all_resumes_results = db_manager.find({})
                                            st.session_state.delete_confirmation = False  # Reset confirmation state
                                        except Exception as e:
                                            st.error(f"Error deleting resume: {e}")
                                with col2:
                                    if st.button("Cancel", key="cancel_delete_button"):
                                        st.info("Deletion canceled.")
                                        st.session_state.delete_confirmation = False  # Reset confirmation state
                    else:
                        st.error("Could not find the selected resume. Please try again.")
    except Exception as e:
        st.error(f"Error connecting to database: {e}")


def job_matcher_page():
    st.title("Job Description Matcher")
    
    # Initialize session state variables
    if 'job_matcher_results' not in st.session_state:
        st.session_state.job_matcher_results = []
    if 'extracted_keywords' not in st.session_state:
        st.session_state.extracted_keywords = set()
    
    # Job description input
    job_description = st.text_area("Enter Job Description", height=200)
    
    if st.button("Find Matching Candidates"):
        if not job_description.strip():
            st.error("Please enter a job description")
            return
            
        # Create progress bar and status text
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Find matching candidates
        matcher = JobMatcher()
        st.session_state.job_matcher_results = matcher.find_matching_candidates(
            job_description, 
            progress_bar=progress_bar,
            status_text=status_text
        )
        
        # Clear progress indicators
        progress_bar.empty()
        status_text.empty()
    
    # Display results if available
    if st.session_state.job_matcher_results:
        st.write("### Matching Candidates")
        
        # Create a table for all candidates
        candidates_data = []
        for candidate in st.session_state.job_matcher_results:
            candidates_data.append({
                "Name": candidate["name"],
                "Score": f"{candidate['score']}%",
                "Status": candidate["status"],
                "Phone": candidate["phone"],
                "Email": candidate["email"]
            })
        
        # Display the table
        st.dataframe(candidates_data)
        
        # Display detailed candidate cards
        st.write("### Candidate Details")
        for candidate in st.session_state.job_matcher_results:
            with st.expander(f"{candidate['name']} - Score: {candidate['score']}%"):
                # Contact information
                st.write(f"**Phone:** {candidate['phone']}")
                st.write(f"**Email:** {candidate['email']}")
                
                # Create two columns for buttons
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button("📊 View Matching Analysis", key=f"analysis_{candidate['mongo_id']}"):
                        st.write("**Matching Analysis:**")
                        st.write(candidate['reason'])
                
                with col2:
                    if st.button("🔄 Retailor Resume", key=f"retailor_{candidate['mongo_id']}"):
                        with st.spinner("Retailoring resume..."):
                            safe_resume = convert_objectid_to_str(candidate["resume"])
                            new_res = matcher.resume_retailor.retailor_resume(
                            safe_resume,
                            st.session_state.extracted_keywords
                        )
                            if new_res:
                                st.success("Resume retailored successfully!")
                                # Create a downloadable JSON file
                                json_str = json.dumps(new_res, indent=2)
                                st.download_button(
                                    label="📥 Download Retailored Resume",
                                    data=json_str,
                                    file_name=f"retailored_resume_{candidate['name'].replace(' ', '_')}.json",
                                    mime="application/json",
                                    key=f"download_{candidate['mongo_id']}"
                                )
                                # Show the retailored resume
                                st.write("### Retailored Resume")
                                st.json(new_res)
                
                # Show full resume button
                if st.button("📄 View Full Resume", key=f"view_{candidate['mongo_id']}"):
                    st.json(candidate['resume'])


def convert_objectid_to_str(obj):
    if isinstance(obj, dict):
        return {k: convert_objectid_to_str(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_objectid_to_str(i) for i in obj]
    elif type(obj).__name__ == "ObjectId":
        return str(obj)
    else:
        return obj

