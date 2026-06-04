from django.contrib import admin
from .models import FaceEmbedding


@admin.register(FaceEmbedding)
class FaceEmbeddingAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'num_samples', 'intra_sim_mean',
        'quality_label', 'is_active', 'updated_at',
    )
    list_filter = ('is_active',)
    search_fields = ('user__full_name', 'user__roll_no')
    readonly_fields = ('embedding_dim', 'created_at', 'updated_at')