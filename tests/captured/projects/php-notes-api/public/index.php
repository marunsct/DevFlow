<?php

declare(strict_types=1);

require __DIR__ . '/../vendor/autoload.php';

// Create the Slim application and run it.
// $app->run() creates a ServerRequest from $_SERVER/$GLOBALS,
// processes it through middleware and routes, then sends the
// PSR-7 response (headers + body) back to PHP's built-in server.
$app = \NotesApi\Service::createApp();
$app->run();
