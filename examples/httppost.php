<?php
$response = "";
$apiKey = 'changethistosomethingthenpassinheaders';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $message = $_POST['message'] ?? '';

    if ($message === '') {
        $response = "Please enter a message.";
    } else {
        // Prepare POST data for the websocket server endpoint
        $postData = http_build_query(['message' => $message]);

        $opts = [
            'http' => [
                'method'  => 'POST',
                'header'  => "Content-Type: application/x-www-form-urlencoded\r\n" .
                             "X-API-Key: $apiKey\r\n",
                'content' => $postData,
                'timeout' => 5
            ]
        ];

        $context = stream_context_create($opts);

        // Replace with your actual URL:
        $url = "https://twizt3d.net/wss/post";

        $result = @file_get_contents($url, false, $context);

        if ($result === FALSE) {
            $response = "Failed to send message.";
        } else {
            $response = "Message sent successfully!";
        }
    }
}
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <title>Send Message to WebSocket Server</title>
</head>
<body>
    <h2>Send Message to WebSocket Server</h2>

    <?php if ($response): ?>
        <p><strong><?php echo htmlspecialchars($response); ?></strong></p>
    <?php endif; ?>

    <form method="POST" action="">
        <label for="message">Message:</label><br />
        <textarea id="message" name="message" rows="4" cols="50" required></textarea><br /><br />
        <button type="submit">Send</button>
    </form>
</body>
</html>
