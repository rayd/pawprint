// Basic AJAX requestor

Pawprint.Requestor = {
	// mapping of known error codes to client-side explanations
	ERROR_CODES: {
		"401": "Username and/or password are incorrect",
		"405": "The specified server does not support RPC",
		"-32601": "This feature is not supported by your Trac server"
	}
};
