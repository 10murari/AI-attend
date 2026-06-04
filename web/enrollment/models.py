from django.db import models
from django.conf import settings


class FaceEmbedding(models.Model):
    """
    Face embedding for a student.
    Stores the 512-D centroid embedding as binary data.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='face_embedding',
        limit_choices_to={'role': 'student'},
    )
    embedding = models.BinaryField(
        help_text="512-D float32 centroid embedding (2048 bytes)"
    )
    embedding_dim = models.PositiveIntegerField(default=512)
    num_samples = models.PositiveIntegerField(
        default=0,
        help_text="Number of face samples used to compute centroid"
    )
    intra_sim_mean = models.FloatField(
        null=True, blank=True,
        help_text="Mean intra-person cosine similarity (quality metric)"
    )
    intra_sim_min = models.FloatField(null=True, blank=True)
    intra_sim_std = models.FloatField(null=True, blank=True)
    photo_path = models.CharField(
        max_length=500, blank=True,
        help_text="Path to best reference face crop"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['user__roll_no']

    def __str__(self):
        return f"Embedding: {self.user.roll_no} ({self.num_samples} samples)"

    def set_embedding(self, numpy_array):
        """Store numpy array as bytes."""
        import numpy as np
        self.embedding = numpy_array.astype(np.float32).tobytes()

    def get_embedding(self):
        """Load bytes as numpy array."""
        import numpy as np
        return np.frombuffer(bytes(self.embedding), dtype=np.float32).copy()

    @property
    def quality_label(self):
        if self.intra_sim_mean is None:
            return "Unknown"
        if self.intra_sim_mean >= 0.7:
            return "Good"
        elif self.intra_sim_mean >= 0.5:
            return "Fair"
        return "Poor"