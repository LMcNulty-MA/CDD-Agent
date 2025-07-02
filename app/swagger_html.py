def custom_swagger_ui_html():
    """
    Returns custom Swagger UI HTML with dark mode toggle functionality.
    The HTML includes comprehensive styling for both light and dark themes
    and saves the user's theme preference in localStorage.
    """
    return """
<!DOCTYPE html>
<html>
<head>
    <link type="text/css" rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
    <style>
        /* Theme toggle button */
        .theme-switch-container {
            position: fixed;
            top: 10px;
            right: 20px;
            z-index: 1000;
            display: flex;
            align-items: center;
        }
        .theme-switch-label {
            margin-right: 10px;
            color: #000; /* Default color for light mode */
            font-weight: 500;
            font-size: 14px;
        }
        .theme-switch {
            position: relative;
            display: inline-block;
            width: 60px;
            height: 34px;
        }
        .theme-switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }
        .slider {
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: #ccc;
            transition: .4s;
            border-radius: 34px;
        }
        .slider:before {
            position: absolute;
            content: "";
            height: 26px;
            width: 26px;
            left: 4px;
            bottom: 4px;
            background-color: white;
            transition: .4s;
            border-radius: 50%;
        }
        input:checked + .slider {
            background-color: #2196F3;
        }
        input:checked + .slider:before {
            transform: translateX(26px);
        }
        
        /* Dark theme CSS that will be applied when the checkbox is checked */
        body.dark-theme {
            background-color: #1e1e1e;
            color: #ffffff;
        }
        .dark-theme .swagger-ui {
            background-color: #1e1e1e;
            color: #ffffff;
        }
        .dark-theme .swagger-ui .topbar {
            background-color: #252526;
            border-bottom: 1px solid #444444;
        }
        .dark-theme .theme-switch-label {
            color: #ffffff;
        }
        .dark-theme .swagger-ui .info .title,
        .dark-theme .swagger-ui .info .base-url,
        .dark-theme .swagger-ui .info li,
        .dark-theme .swagger-ui .info p,
        .dark-theme .swagger-ui .info h1,
        .dark-theme .swagger-ui .info h2,
        .dark-theme .swagger-ui .info h3,
        .dark-theme .swagger-ui .info h4,
        .dark-theme .swagger-ui .info h5 {
            color: #ffffff;
        }
        .dark-theme .swagger-ui .opblock-tag,
        .dark-theme .swagger-ui .opblock .opblock-summary-operation-id,
        .dark-theme .swagger-ui .opblock .opblock-summary-path,
        .dark-theme .swagger-ui .opblock .opblock-summary-path__deprecated,
        .dark-theme .swagger-ui .opblock .opblock-summary-description,
        .dark-theme .swagger-ui .opblock-description-wrapper p,
        .dark-theme .swagger-ui .responses-inner h4,
        .dark-theme .swagger-ui .responses-inner h5,
        .dark-theme .swagger-ui table thead tr td,
        .dark-theme .swagger-ui table thead tr th,
        .dark-theme .swagger-ui .response-col_status,
        .dark-theme .swagger-ui .parameter__name,
        .dark-theme .swagger-ui .parameter__type,
        .dark-theme .swagger-ui .parameter__deprecated,
        .dark-theme .swagger-ui .parameter__in,
        .dark-theme .swagger-ui .btn,
        .dark-theme .swagger-ui .execute-wrapper .btn {
            color: #ffffff;
        }
        .dark-theme .swagger-ui .opblock {
            background-color: #252526;
            border-color: #444444;
        }
        .dark-theme .swagger-ui .opblock.is-open .opblock-summary {
            border-bottom-color: #444444;
        }
        .dark-theme .swagger-ui .opblock .opblock-section-header {
            background-color: #2d2d2d;
            border-bottom-color: #444444;
        }
        .dark-theme .swagger-ui .btn {
            background-color: #0d5aa7;
            border-color: #0d5aa7;
        }
        .dark-theme .swagger-ui .btn:hover {
            background-color: #1560bd;
            border-color: #1560bd;
        }
        .dark-theme .swagger-ui .scheme-container {
            background-color: #252526;
            border-color: #444444;
        }
        .dark-theme .swagger-ui .model-box,
        .dark-theme .swagger-ui .json-schema-2020-12-head,
        .dark-theme .swagger-ui .json-schema-2020-12-body {
            background-color: #1a1a1a !important;
            background-image: none !important;
            color: #ffffff !important;
            border: 1px solid #444444 !important;
        }
        .dark-theme .swagger-ui .model .property,
        .dark-theme .swagger-ui .json-schema-2020-12 .json-schema-2020-12-property {
            background-color: #1a1a1a !important;
            color: #ffffff !important;
            border-bottom-color: #444444 !important;
        }
        .dark-theme .swagger-ui .model .property .prop-type,
        .dark-theme .swagger-ui .model .property .prop-format,
        .dark-theme .swagger-ui .model .property .prop-enum,
        .dark-theme .swagger-ui .model .property .prop-example,
        .dark-theme .swagger-ui .json-schema-2020-12 .json-schema-2020-12-keyword,
        .dark-theme .swagger-ui .json-schema-2020-12 .json-schema-2020-12-json-viewer {
            color: #ffffff !important;
        }
        .dark-theme .swagger-ui .json-schema-2020-12 .json-schema-2020-12-body {
            background-color: #222222 !important;
            color: #ffffff !important;
        }
        .dark-theme .swagger-ui .json-schema-2020-12 .json-schema-2020-12-accordion,
        .dark-theme .swagger-ui .json-schema-2020-12 .json-schema-2020-12-expand-deep-button {
            background-color: #222222 !important;
            color: #ffffff !important;
        }
        .dark-theme .swagger-ui textarea,
        .dark-theme .swagger-ui input[type="text"],
        .dark-theme .swagger-ui input[type="password"],
        .dark-theme .swagger-ui input[type="search"],
        .dark-theme .swagger-ui input[type="email"],
        .dark-theme .swagger-ui input[type="url"] {
            background-color: #2d2d2d !important;
            color: #ffffff !important;
            border-color: #444444 !important;
        }
        .dark-theme .swagger-ui .response-content-type {
            color: #ffffff;
        }
        .dark-theme .swagger-ui .highlight-code {
            background-color: #1a1a1a !important;
        }
        .dark-theme .swagger-ui .microlight {
            color: #ffffff !important;
        }
        /* Improve readability for parameter tables */
        .dark-theme .swagger-ui table tbody tr td {
            border-color: #444444;
            color: #ffffff;
        }
        .dark-theme .swagger-ui .parameters .parameter .parameter-item-content-type {
            color: #ffffff;
        }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
</head>
<body>
    <div class="theme-switch-container">
        <span class="theme-switch-label">Dark Mode</span>
        <label class="theme-switch">
            <input type="checkbox" id="theme-toggle">
            <span class="slider"></span>
        </label>
    </div>
    <div id="swagger-ui"></div>
    <script>
        const ui = SwaggerUIBundle({
            url: '/cdd-agent/openapi.json',
            dom_id: '#swagger-ui',
            presets: [
                SwaggerUIBundle.presets.apis,
                SwaggerUIBundle.SwaggerUIStandalonePreset
            ],
            layout: "BaseLayout",
            deepLinking: true,
            displayRequestDuration: true,
            tryItOutEnabled: true
        });
        
        // Theme toggle functionality
        const themeToggle = document.getElementById('theme-toggle');
        
        // Check for saved theme preference or prefer-color-scheme
        const prefersDarkScheme = window.matchMedia('(prefers-color-scheme: dark)');
        const savedTheme = localStorage.getItem('cdd-agent-theme');
        
        if (savedTheme === 'dark' || (!savedTheme && prefersDarkScheme.matches)) {
            document.body.classList.add('dark-theme');
            themeToggle.checked = true;
        }
        
        // Add toggle event
        themeToggle.addEventListener('change', function() {
            if (this.checked) {
                document.body.classList.add('dark-theme');
                localStorage.setItem('cdd-agent-theme', 'dark');
            } else {
                document.body.classList.remove('dark-theme');
                localStorage.setItem('cdd-agent-theme', 'light');
            }
        });
        
        // Listen for system theme changes
        prefersDarkScheme.addEventListener('change', function(e) {
            const savedTheme = localStorage.getItem('cdd-agent-theme');
            if (!savedTheme) {
                if (e.matches) {
                    document.body.classList.add('dark-theme');
                    themeToggle.checked = true;
                } else {
                    document.body.classList.remove('dark-theme');
                    themeToggle.checked = false;
                }
            }
        });
    </script>
</body>
</html>
    """ 