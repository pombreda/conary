<?xml version='1.0' encoding='UTF-8'?>
<?python #
import kid; kid.enable_import()
from templates import library
?>

<html xmlns="http://www.w3.org/1999/xhtml" xmlns:py="http://naeblis.cx/ns/kid#">
    {library.html_header(pageTitle)}
    <body>
        <h2>{pageTitle}</h2>
        
        <p class="warning">{error}</p>
        <p>Please go back and try again.</p>

        {library.html_footer()}
    </body>
</html>
