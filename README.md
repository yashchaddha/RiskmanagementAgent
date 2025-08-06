# Risk Management Agent

An AI-powered risk assessment and compliance management platform that helps organizations identify, assess, and manage risks effectively.

## Features

- **AI-Powered Risk Assessment**: Generate organization-specific risks using advanced AI
- **Risk Register Management**: Comprehensive risk tracking and management
- **Compliance Framework Support**: Built-in compliance frameworks and guidelines
- **User Preference Management**: Customizable risk assessment preferences
- **Finalized Risks Summary**: Generate comprehensive risk assessment reports based on finalized risks
- **Real-time Chat Interface**: Interactive AI assistant for risk management queries

## Key Features

### Finalized Risks Summary
The system now generates comprehensive risk assessment summaries based on the risks that users have finalized. This feature provides:

- **Executive Summary**: Overview of total risks and critical concerns
- **Risk Distribution Analysis**: Breakdown by categories, likelihood, and impact
- **Department and Ownership Analysis**: Risk distribution across departments
- **Treatment Strategy Overview**: Common mitigation approaches and resource requirements
- **Compliance and Security Considerations**: Regulatory implications and security impact
- **Next Steps and Recommendations**: Actionable recommendations and priorities

To generate a finalized risks summary:
1. Finalize risks through the risk table interface
2. Click the "📊 Finalized Risks Summary" button in the chatbot header
3. Or use the "Generate finalized risks summary" quick action

## Installation and Setup

### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
python setup_env.py
```

5. Start the backend server:
```bash
python main.py
```

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Start the development server:
```bash
npm run dev
```

## API Endpoints

### Risk Summary Endpoints

- `GET /risk-summary/finalized` - Generate comprehensive summary based on finalized risks
- `POST /risk-summary` - Generate summary based on conversation history (legacy)

### Risk Management Endpoints

- `POST /risks/finalize` - Finalize selected risks
- `GET /risks/finalized` - Get user's finalized risks
- `POST /risks/save` - Save generated risks to database
- `GET /risks/user` - Get all risks for current user

## Usage

1. **Sign up/Login**: Create an account or log in with existing credentials
2. **Generate Risks**: Use the chatbot to generate organization-specific risks
3. **Review and Select**: Review generated risks and select relevant ones
4. **Finalize Risks**: Finalize selected risks with additional details
5. **Generate Summary**: Create comprehensive risk assessment reports based on finalized risks

## Technology Stack

- **Backend**: FastAPI, Python, MongoDB
- **Frontend**: React, TypeScript, Vite
- **AI**: OpenAI GPT models
- **Authentication**: JWT tokens
- **Database**: MongoDB with PyMongo

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is licensed under the MIT License. 