// Basic AJAX requestor

Pawprint.Requestor = {
	// mapping of known error codes to client-side explanations
	ERROR_CODES: {
		"401": "Username and/or password are incorrect",
		"404": "The specified Trac server cannot be found",
		"405": "The specified Trac server does not support RPC",
		"327": "This feature is not supported by your Trac server",
		"317": "Your session has ended. Please login again."
	}
};
